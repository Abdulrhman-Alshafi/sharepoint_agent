
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.config import settings
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.services.graph_api_client import GraphAPIClient

async def test_page_creation():
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, settings.SITE_ID)
    
    print(f"Testing page creation for site: {settings.SITE_ID}")
    
    endpoint = f"/sites/{settings.SITE_ID}/pages"
    payload = {
        "name": "TestPageByAntigravity.aspx",
        "title": "Test Page By Antigravity",
        "pageLayout": "article"
    }
    
    print("\nTrying v1.0...")
    try:
        response = await graph_client.post(endpoint, payload)
        print("SUCCESS v1.0!")
        print(response)
    except Exception as e:
        print(f"FAILED v1.0: {e}")
        
    print("\nTrying beta...")
    try:
        response = await graph_client.post_beta(endpoint, payload)
        print("SUCCESS beta!")
        print(response)
    except Exception as e:
        print(f"FAILED beta: {e}")

if __name__ == "__main__":
    asyncio.run(test_page_creation())
