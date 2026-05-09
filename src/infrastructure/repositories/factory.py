"""Repository factory to create specific repositories."""

from typing import Optional
from src.infrastructure.services.sharepoint.site_service import SiteService
from src.infrastructure.services.sharepoint.list_service import ListService
from src.infrastructure.services.sharepoint.page_service import PageService
from src.infrastructure.services.sharepoint.library_service import LibraryService
from src.infrastructure.services.sharepoint.drive_service import DriveService
from src.infrastructure.services.sharepoint.permission_service import PermissionService
from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
from src.infrastructure.services.graph_api_client import GraphAPIClient
from src.infrastructure.services.rest_api_client import RESTAPIClient
from src.infrastructure.services.authentication_service import AuthenticationService
from src.infrastructure.config import settings

def get_site_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
    return SiteService(graph_client, rest_client)

def get_list_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    return ListService(graph_client)

def get_page_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
    return PageService(rest_client, graph_client)

def get_library_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    return LibraryService(graph_client)

def get_drive_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    return DriveService(graph_client)

def get_permission_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
    return PermissionService(rest_client)

def get_enterprise_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    target_site = site_id or settings.SITE_ID
    auth_service = AuthenticationService()
    graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
    rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
    return EnterpriseService(graph_client, rest_client)
