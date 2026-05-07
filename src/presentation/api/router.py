"""API router configuration."""

from fastapi import APIRouter
from src.presentation.api.routes import (
    chat_controller,
    file_controller,
    library_controller,
    provision_controller,
    query_controller,
)

api_router = APIRouter()

api_router.include_router(chat_controller.router, prefix="/chat", tags=["Chat & Actions"])
api_router.include_router(file_controller.router, prefix="/files", tags=["File Management"])
api_router.include_router(library_controller.router, prefix="/libraries", tags=["Document Libraries"])
api_router.include_router(provision_controller.router, prefix="/provision", tags=["Provisioning"])
api_router.include_router(query_controller.router, prefix="/query", tags=["Data Queries"])
