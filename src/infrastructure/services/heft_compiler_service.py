"""Heft build service for SPFx 1.22+ custom React web parts."""

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.domain.entities import CustomWebPartCode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns that should NEVER appear in AI-generated React / SCSS content.
# These indicate potential prompt-injection or supply-chain attacks.
# ---------------------------------------------------------------------------
_FORBIDDEN_TSX_PATTERNS: list[re.Pattern] = [
    # Node.js child_process / shell execution
    re.compile(r"\bchild_process\b", re.IGNORECASE),
    re.compile(r"\bexecSync\b|\bspawnSync\b|\bexecFileSync\b", re.IGNORECASE),
    # Dynamic require / import with variable (eval-like)
    re.compile(r"\brequire\s*\((?!\s*['\"])", re.IGNORECASE),
    re.compile(r"\bimport\s*\((?!\s*['\"])", re.IGNORECASE),
    # Filesystem access
    re.compile(r"\bfs\s*\.\s*(write|unlink|rm|mkdir|readFile)", re.IGNORECASE),
    # eval / Function constructor
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bnew\s+Function\s*\(", re.IGNORECASE),
    # Network requests not going through React component props
    re.compile(r"\bnew\s+XMLHttpRequest\b", re.IGNORECASE),
    re.compile(r"\bfetch\s*\(\s*['\"`]https?://(?!graph\.microsoft\.com)", re.IGNORECASE),
    # process.env access (secrets exfil)
    re.compile(r"\bprocess\s*\.\s*env\b", re.IGNORECASE),
    # Inline script tags (XSS injection inside JSX)
    re.compile(r"<\s*script\b", re.IGNORECASE),
    # dangerouslySetInnerHTML is a red flag in AI-generated code
    re.compile(r"dangerouslySetInnerHTML", re.IGNORECASE),
]

_FORBIDDEN_SCSS_PATTERNS: list[re.Pattern] = [
    # CSS expressions that execute JS (IE legacy attack vector)
    re.compile(r"\bexpression\s*\(", re.IGNORECASE),
    # Exfil via url() pointing outside expected origins
    re.compile(r"url\s*\(\s*['\"]?https?://(?!fonts\.googleapis\.com|fonts\.gstatic\.com)", re.IGNORECASE),
]

# Maximum allowed file size (bytes) for AI-generated sources
_MAX_TSX_BYTES = 100_000  # 100 KB
_MAX_SCSS_BYTES = 50_000  # 50 KB


class ContentValidationError(ValueError):
    """Raised when AI-generated code fails pre-write security validation."""


def _validate_tsx(content: str) -> None:
    """Raise ContentValidationError if TSX content looks malicious."""
    if len(content.encode()) > _MAX_TSX_BYTES:
        raise ContentValidationError(
            f"AI-generated TSX exceeds the {_MAX_TSX_BYTES // 1000} KB size limit."
        )
    for pattern in _FORBIDDEN_TSX_PATTERNS:
        if pattern.search(content):
            raise ContentValidationError(
                f"AI-generated TSX contains a forbidden pattern: `{pattern.pattern}`. "
                "Aborting build for security reasons."
            )


def _validate_scss(content: str) -> None:
    """Raise ContentValidationError if SCSS content looks malicious."""
    if len(content.encode()) > _MAX_SCSS_BYTES:
        raise ContentValidationError(
            f"AI-generated SCSS exceeds the {_MAX_SCSS_BYTES // 1000} KB size limit."
        )
    for pattern in _FORBIDDEN_SCSS_PATTERNS:
        if pattern.search(content):
            raise ContentValidationError(
                f"AI-generated SCSS contains a forbidden pattern: `{pattern.pattern}`. "
                "Aborting build for security reasons."
            )


class HeftCompilerService:
    """Service responsible for building SPFx custom web parts with Heft."""

    def __init__(self, template_root: Optional[Path] = None):
        self.template_root = template_root or Path(__file__).resolve().parents[3] / "templates" / "spfx-base-heft"
        self.temporary_workdir: Optional[Path] = None

    def compile_custom_webpart(self, custom_component: CustomWebPartCode) -> Path:
        """Validate, then compile a custom web part from a template and return the .sppkg path."""
        if not self.template_root.exists():
            raise FileNotFoundError(
                f"SPFx Heft template not found at {self.template_root}. "
                "Please ensure ./templates/spfx-base-heft exists and contains a valid SPFx 1.22+ project."
            )

        # ---------------------------------------------------------------
        # SECURITY: validate AI-generated content before writing to disk
        # ---------------------------------------------------------------
        _validate_tsx(custom_component.tsx_content)
        _validate_scss(custom_component.scss_content)
        logger.info("AI-generated component '%s' passed content validation.", custom_component.component_name)

        self.temporary_workdir = Path(tempfile.mkdtemp(prefix="heft_build_"))
        try:
            shutil.copytree(self.template_root, self.temporary_workdir, dirs_exist_ok=True)
            self._write_custom_component(self.temporary_workdir, custom_component)

            self._run_command(["npm", "install"], cwd=self.temporary_workdir)
            self._run_command(["npx", "heft", "build", "--production"], cwd=self.temporary_workdir, timeout=300)
            self._run_command(["npx", "heft", "package-solution", "--production"], cwd=self.temporary_workdir)

            package_path = self._find_sppkg(self.temporary_workdir)
            if package_path is None:
                raise FileNotFoundError("Generated .sppkg package not found after Heft build")

            return package_path
        except Exception:
            self.cleanup_workspace()
            raise

    def cleanup_workspace(self) -> None:
        """Delete the temporary build workspace and all generated files."""
        if self.temporary_workdir and self.temporary_workdir.exists():
            shutil.rmtree(self.temporary_workdir, ignore_errors=True)
        self.temporary_workdir = None

    def _write_custom_component(self, workdir: Path, custom_component: CustomWebPartCode) -> None:
        tsx_file = self._find_file(workdir, suffix=".tsx")
        scss_file = self._find_file(workdir, suffix=".scss")

        if tsx_file is None:
            raise FileNotFoundError("Unable to find a React .tsx file to overwrite in the SPFx template")
        if scss_file is None:
            raise FileNotFoundError("Unable to find an SCSS file to overwrite in the SPFx template")

        tsx_file.write_text(custom_component.tsx_content, encoding="utf-8")
        scss_file.write_text(custom_component.scss_content, encoding="utf-8")

    def _find_file(self, root: Path, suffix: str) -> Optional[Path]:
        files = [path for path in root.rglob(f"*{suffix}") if path.is_file()]
        return sorted(files, key=lambda path: len(str(path)))[0] if files else None

    def _run_command(self, command: list[str], cwd: Path, timeout: Optional[int] = None) -> None:
        process = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"Command '{' '.join(command)}' failed with exit code {process.returncode}: "
                f"stdout={process.stdout.strip()} stderr={process.stderr.strip()}"
            )

    def _find_sppkg(self, workdir: Path) -> Optional[Path]:
        solution_root = workdir / "sharepoint" / "solution"
        if solution_root.exists():
            candidate = next(solution_root.rglob("*.sppkg"), None)
            if candidate:
                return candidate

        return next(workdir.rglob("*.sppkg"), None)
