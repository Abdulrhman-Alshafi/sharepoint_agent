"""Service for Graph API batch operations."""

from typing import Dict, Any, List
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.services.graph_api_client import GraphAPIClient


class BatchOperationsService:
    """Handles Microsoft Graph API $batch operations for bulk data operations."""

    # Graph API maximum batch size
    MAX_BATCH_SIZE = 20

    def __init__(self, graph_client: GraphAPIClient):
        """Initialize batch operations service.
        
        Args:
            graph_client: Graph API client for making requests
        """
        self.graph_client = graph_client

    async def seed_list_data(
        self,
        list_id: str,
        seed_data: List[Dict[str, Any]],
        site_id: str = None
    ) -> bool:
        """Seed a SharePoint list with data using batch operations.
        
        Args:
            list_id: SharePoint list ID
            seed_data: List of items to insert (dicts with field values)
            
        Returns:
            True if successful
            
        Raises:
            SharePointProvisioningException: If batch operations fail
        """
        if not seed_data:
            return True
        
        failed_inserts = []
        
        def process_batch_response(resp_json: Dict[str, Any]) -> None:
            """Process batch response and collect failures."""
            for sub in resp_json.get("responses", []):
                if sub.get("status", 500) not in (200, 201):
                    err_msg = sub.get("body", {}).get("error", {}).get("message", "Unknown error")
                    failed_inserts.append(f"Item ID {sub.get('id')} failed: {err_msg}")

        # Process in batches
        batch_payload: Dict[str, List[Dict[str, Any]]] = {"requests": []}
        batch_id = 1
        _site_id = site_id or self.graph_client.site_id
        
        for item in seed_data:
            batch_payload["requests"].append({
                "id": str(batch_id),
                "method": "POST",
                "url": f"/sites/{_site_id}/lists/{list_id}/items",
                "headers": {"Content-Type": "application/json"},
                "body": {"fields": item}
            })
            batch_id += 1
            
            # Send batch when full
            if len(batch_payload["requests"]) == self.MAX_BATCH_SIZE:
                batch_resp = await self.graph_client.post(
                    "/$batch",
                    batch_payload,
                )
                process_batch_response(batch_resp)
                # Clear for next batch
                batch_payload = {"requests": []}

        # Send remaining items
        if batch_payload["requests"]:
            batch_resp = await self.graph_client.post(
                "/$batch",
                batch_payload,
            )
            process_batch_response(batch_resp)
        
        if failed_inserts:
            raise SharePointProvisioningException(
                f"Data seeding partially failed. Errors: {' | '.join(failed_inserts)}"
            )
        
        return True
