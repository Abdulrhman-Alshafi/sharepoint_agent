"""Backwards-compatible shim.

GraphAPISharePointRepository has been moved to graph_sharepoint_repository.py.
Import via:
    from src.infrastructure.repositories import GraphAPISharePointRepository
"""

__all__ = ["GraphAPISharePointRepository"]


def __getattr__(name: str):
    """Lazy-load heavy classes to avoid circular imports at package init time.

    Service modules (drive_service, enterprise_service, …) import utils from
    this package.  If we eagerly import GraphAPISharePointRepository here we
    create a circular dependency because that class in turn imports those very
    service modules.  The module-level __getattr__ defers the import until the
    name is first accessed, breaking the cycle.
    """
    if name == "GraphAPISharePointRepository":
        from src.infrastructure.repositories.graph_sharepoint_repository import (  # noqa: PLC0415
            GraphAPISharePointRepository,
        )
        return GraphAPISharePointRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
