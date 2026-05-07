"""API Routes.

Thin HTTP controllers delegating business logic to orchestrators.
"""

from src.presentation.api.routes.chat_controller import router as chat_router

__all__ = ["chat_router"]
