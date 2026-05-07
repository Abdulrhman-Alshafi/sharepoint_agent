"""Service for SharePoint data seeding operations."""

from typing import Dict, Any, List
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.batch_operations_service import BatchOperationsService
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors


class DataService:
    """Handles SharePoint data seeding and batch operations."""

    def __init__(self, batch_service: BatchOperationsService):
        """Initialize data service.
        
        Args:
            batch_service: Batch operations service for bulk data operations
        """
        self.batch_service = batch_service

    @handle_sharepoint_errors("seed list data")
    async def seed_list_data(
        self,
        list_id: str,
        seed_data: List[Dict[str, Any]],
        site_id: str = None
    ) -> bool:
        """Seed a list with data items via Graph API Batching."""
        return await self.batch_service.seed_list_data(list_id, seed_data, site_id=site_id)
