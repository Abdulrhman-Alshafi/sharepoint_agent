"""Governance service — enforces naming and permission policies before operations execute."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------

_RESERVED_NAMES = frozenset({"admin", "root", "system", "sharepoint", "microsoft",
                               "test", "temp", "tmp", "delete", "null"})
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}[a-z0-9]$|^[a-z0-9]{1,2}$")
_MAX_TITLE_LEN = 80
_DANGEROUS_PERMISSIONS = frozenset({"full control", "design", "manage hierarchy"})


@dataclass
class GovernanceViolation:
    rule: str
    message: str
    is_blocking: bool = True   # False → warning only


class GovernanceService:
    """Evaluate resource requests against enterprise governance rules.

    Call ``GovernanceService.check_site(...)`` / ``check_page(...)`` before
    creating or updating a resource.  Non-blocking violations are logged as
    warnings; blocking violations should prevent the operation.
    """

    # ------------------------------------------------------------------
    # Site checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_site(
        title: str,
        name: str,
        template: Optional[str] = None,
        owner_email: Optional[str] = None,
    ) -> List[GovernanceViolation]:
        violations: List[GovernanceViolation] = []

        # 1. Title length
        if len(title) > _MAX_TITLE_LEN:
            violations.append(GovernanceViolation(
                rule="SITE_TITLE_TOO_LONG",
                message=f"Site title must be ≤{_MAX_TITLE_LEN} characters (got {len(title)}).",
            ))

        # 2. Reserved names
        if name.lower() in _RESERVED_NAMES or title.lower() in _RESERVED_NAMES:
            violations.append(GovernanceViolation(
                rule="RESERVED_NAME",
                message=f"'{name or title}' is a reserved system name.",
            ))

        # 3. URL slug format
        if name and not _SLUG_RE.match(name.lower()):
            violations.append(GovernanceViolation(
                rule="INVALID_SITE_NAME_SLUG",
                message=f"Site URL slug '{name}' must be 3-64 lowercase alphanumeric chars/hyphens, "
                         "start and end with alphanumeric.",
                is_blocking=False,
            ))

        # 4. Owner email presence (warning only)
        if not owner_email:
            violations.append(GovernanceViolation(
                rule="MISSING_SITE_OWNER",
                message="No owner email specified. Defaulting to the authenticated service account.",
                is_blocking=False,
            ))

        for v in violations:
            level = "WARNING" if not v.is_blocking else "BLOCK"
            logger.info("[GOVERNANCE][%s] %s: %s", level, v.rule, v.message)

        return violations

    # ------------------------------------------------------------------
    # Page checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_page(title: str, layout: Optional[str] = None) -> List[GovernanceViolation]:
        violations: List[GovernanceViolation] = []

        if len(title) > _MAX_TITLE_LEN:
            violations.append(GovernanceViolation(
                rule="PAGE_TITLE_TOO_LONG",
                message=f"Page title must be ≤{_MAX_TITLE_LEN} characters (got {len(title)}).",
            ))

        if not title.strip():
            violations.append(GovernanceViolation(
                rule="EMPTY_PAGE_TITLE",
                message="Page title cannot be empty.",
            ))

        for v in violations:
            level = "WARNING" if not v.is_blocking else "BLOCK"
            logger.info("[GOVERNANCE][%s] %s: %s", level, v.rule, v.message)

        return violations

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_permission(permission_level: str) -> List[GovernanceViolation]:
        violations: List[GovernanceViolation] = []
        if permission_level.lower() in _DANGEROUS_PERMISSIONS:
            violations.append(GovernanceViolation(
                rule="HIGH_PRIVILEGE_PERMISSION",
                message=f"'{permission_level}' grants full administrative access. "
                         "Ensure this is intentional.",
                is_blocking=False,
            ))
        return violations

    # ------------------------------------------------------------------
    # Helper: raise if any blocking violations exist
    # ------------------------------------------------------------------

    @staticmethod
    def assert_no_blocks(violations: List[GovernanceViolation], context: str = "") -> None:
        blocking = [v for v in violations if v.is_blocking]
        if blocking:
            msgs = "; ".join(v.message for v in blocking)
            raise ValueError(f"Governance policy blocked{' ' + context if context else ''}: {msgs}")
