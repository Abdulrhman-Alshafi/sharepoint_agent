"""Upload service — file validation and upload execution.

Extracts all file upload logic from chat.py into a reusable service.
No FastAPI dependencies.
"""

import logging
import os
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".csv", ".msg", ".png", ".jpg", ".jpeg", ".gif", ".mp4",
})

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def validate_uploads(
    uploads: List[Tuple[str, bytes, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Validate a list of uploaded files.

    Args:
        uploads: List of (filename, file_bytes, content_type) tuples.

    Returns:
        (validated_files, errors) where validated_files is a list of dicts
        with keys: bytes, filename, content_type.
    """
    validated: List[Dict[str, Any]] = []
    errors: List[str] = []

    for filename, file_bytes, content_type in uploads:
        fname = (filename or "unnamed_file").strip()
        ext = os.path.splitext(fname)[1].lower()

        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append(
                f"❌ **{fname}** has an unsupported type (`{ext}`). "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            )
            continue

        if len(file_bytes) == 0:
            errors.append(f"❌ **{fname}** is empty and was skipped.")
            continue

        if len(file_bytes) > MAX_UPLOAD_BYTES:
            errors.append(
                f"❌ **{fname}** is {len(file_bytes)/1024/1024:.1f} MB "
                f"which exceeds the 50 MB limit."
            )
            continue

        validated.append({
            "bytes": file_bytes,
            "filename": fname,
            "content_type": content_type or "application/octet-stream",
        })

    return validated, errors


async def execute_uploads(
    validated_files: List[Dict[str, Any]],
    library_id: str,
    library_name: str,
    repo: Any,
) -> Tuple[List[str], List[str], str]:
    """Upload validated files to a SharePoint library.

    Args:
        validated_files: Files that passed validation.
        library_id: Target library ID.
        library_name: Library display name (for messages).
        repo: SharePoint repository instance.

    Returns:
        (success_lines, fail_lines, last_url)
    """
    success_lines: List[str] = []
    fail_lines: List[str] = []
    last_url = ""

    for vf in validated_files:
        try:
            result = await repo.upload_file(
                library_id=library_id,
                file_name=vf["filename"],
                file_content=vf["bytes"],
            )
            web_url = result.web_url or ""
            size_kb = len(vf["bytes"]) // 1024
            link = (
                f"[📄 {vf['filename']}]({web_url})" if web_url
                else f"**{vf['filename']}**"
            )
            success_lines.append(f"✅ {link} ({size_kb} KB)")
            if web_url:
                last_url = web_url
        except Exception as upload_err:
            logger.error(
                "Upload failed for %s: %s", vf["filename"], upload_err, exc_info=True
            )
            fail_lines.append(f"❌ **{vf['filename']}** failed: {upload_err}")

    return success_lines, fail_lines, last_url


def format_upload_response(
    success_lines: List[str],
    fail_lines: List[str],
    library_name: str,
    pre_errors: Optional[List[str]] = None,
) -> str:
    """Format the upload result into a user-facing message."""
    parts = [f"Uploaded to **{library_name}**:"] + success_lines
    if fail_lines:
        parts += [""] + fail_lines
    if pre_errors:
        parts = pre_errors + [""] + parts
    return "\n".join(parts)


def format_pending_upload_prompt(
    validated_files: List[Dict[str, Any]],
    libraries: List[Dict[str, Any]],
    named_library: Optional[str] = None,
    message: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Build a prompt asking the user which library to upload to.

    Returns:
        (intro_text, lib_names_list)
    """
    filename = validated_files[0]["filename"] if validated_files else "file"
    file_label = (
        f"**{filename}**" if len(validated_files) == 1
        else f"**{len(validated_files)} files** ({', '.join(vf['filename'] for vf in validated_files)})"
    )

    lib_names = [
        lib.get("displayName") or lib.get("name", "Unknown")
        for lib in libraries[:8]
    ]

    if named_library:
        intro = (
            f"📎 I have {file_label} ready, but couldn't find a library named "
            f'**"{named_library}"**. Please pick one of the available libraries:'
        )
    elif message and message.strip():
        intro = (
            f"📎 I have {file_label} ready. I wasn't sure which library you meant — "
            f"please pick one:"
        )
    else:
        intro = f"📎 I have {file_label} ready to upload. Which library should I add it to?"

    return intro, lib_names
