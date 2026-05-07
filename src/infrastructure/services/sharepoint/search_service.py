"""Service for SharePoint-wide search using Microsoft Graph or SharePoint Search API."""

from typing import List, Dict, Any
from src.infrastructure.services.graph_api_client import GraphAPIClient

class SearchService:
    def __init__(self, graph_client: GraphAPIClient):
        self.graph_client = graph_client

    async def search_sharepoint(self, query: str, entity_types: List[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a SharePoint-wide search for documents, lists, sites, etc.
        Uses Microsoft Graph Search API (v1.0).
        Args:
            query: The search query string
            entity_types: Optional list of entity types (e.g., ['driveItem', 'listItem', 'site'])
        Returns:
            List of search results
        """
        endpoint = "/search/query"
        payload = {
            "requests": [
                {
                    "entityTypes": entity_types or ["driveItem", "listItem", "site"],
                    "query": {"queryString": query}
                }
            ]
        }
        data = await self.graph_client.post(endpoint, payload)
        results = []
        for resp in data.get("value", []):
            for hit in resp.get("hitsContainers", []):
                results.extend(hit.get("hits", []))
        return results
