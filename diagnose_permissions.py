#!/usr/bin/env python3
"""Diagnostic script to verify authentication and permissions."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.infrastructure.config import settings
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.services.graph_api_client import GraphAPIClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def diagnose_permissions():
    """Check if the app can authenticate and what permissions it has."""
    
    logger.info("=" * 60)
    logger.info("SharePoint AI - Authentication & Permissions Diagnostic")
    logger.info("=" * 60)
    
    # Check settings
    logger.info(f"\nConfiguration:")
    logger.info(f"  TENANT_ID: {settings.TENANT_ID}")
    logger.info(f"  CLIENT_ID: {settings.CLIENT_ID[:8]}...")
    logger.info(f"  USE_APP_ONLY_AUTH: {settings.USE_APP_ONLY_AUTH}")
    logger.info(f"  SITE_ID: {settings.SITE_ID[:50]}...")
    
    # Initialize auth service
    auth_service = AuthenticationService()
    
    try:
        # Test 1: Get app-only token
        logger.info("\n[Test 1] Acquiring app-only token...")
        token = await auth_service.get_graph_access_token()
        logger.info("✓ App-only token acquired successfully")
        
        # Decode JWT to see token claims (without verification for diagnostic purposes)
        import base64
        import json
        try:
            # JWT format: header.payload.signature
            parts = token.split('.')
            if len(parts) == 3:
                # Add padding if needed
                payload_str = parts[1] + '=' * (4 - len(parts[1]) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload_str))
                logger.info(f"\nToken Claims:")
                logger.info(f"  appid: {decoded.get('appid')}")
                logger.info(f"  iss: {decoded.get('iss')}")
                logger.info(f"  scp: {decoded.get('scp', 'N/A')}")  # App-only has 'roles', delegated has 'scp'
                logger.info(f"  roles: {decoded.get('roles', [])}")  # Check if roles are present
        except Exception as e:
            logger.warning(f"Could not decode token: {e}")
        
        # Test 2: Get Graph API headers
        logger.info("\n[Test 2] Getting Graph API headers...")
        headers = await auth_service.get_graph_headers()
        logger.info("✓ Graph API headers generated")
        logger.info(f"  Authorization header length: {len(headers['Authorization'])}")
        
        # Test 3: Attempt to call /me endpoint
        logger.info("\n[Test 3] Calling /me endpoint...")
        graph_client = GraphAPIClient(auth_service, settings.SITE_ID)
        try:
            me_data = await graph_client.get("/me")
            logger.info("✓ /me endpoint successful")
            logger.info(f"  User: {me_data.get('userPrincipalName', me_data.get('id'))}")
        except Exception as e:
            logger.error(f"✗ /me endpoint failed: {e}")
        
        # Test 4: Check app roles (application permissions)
        logger.info("\n[Test 4] Checking application permissions...")
        logger.info("  Note: Application permissions are listed in token 'roles' claim")
        logger.info("  (See token claims above)")
        
        # Test 5: Test site operations
        logger.info("\n[Test 5] Testing site operations...")
        try:
            logger.info(f"  Attempting to list sites...")
            sites_data = await graph_client.get("/sites?search=*&$top=1")
            logger.info(f"✓ Can query sites endpoint")
            logger.info(f"  Found {sites_data.get('value', []).__len__()} sites")
        except Exception as e:
            logger.error(f"✗ Site query failed: {e}")
        
        logger.info("\n" + "=" * 60)
        logger.info("RECOMMENDATIONS:")
        logger.info("=" * 60)
        logger.info("\nIf you see 'Permission Denied' errors:")
        logger.info("1. Check the 'roles' claim in the token above")
        logger.info("2. Ensure Sites.Manage.All or Sites.ReadWrite.All is granted as APPLICATION permission")
        logger.info("3. Verify the app has Sites.ReadWrite.All (Application) for SITE CREATION")
        logger.info("4. If issues persist, consider switching to OBO mode: USE_APP_ONLY_AUTH=false")
        
    except Exception as e:
        logger.error(f"Diagnostic failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(diagnose_permissions())
