"""Dependency injection and providers for API endpoints."""

import threading
from typing import Callable, Optional
from src.domain.services import BlueprintGeneratorService, DataQueryService
from src.domain.services.intent_classification import IntentClassificationService
from src.application.services import ProvisioningApplicationService, DataQueryApplicationService


class ServiceContainer:
    """Container for application services and dependencies."""
    
    _blueprint_generator: Optional[BlueprintGeneratorService] = None
    _provisioning_service: Optional[ProvisioningApplicationService] = None
    _data_query_service: Optional[DataQueryApplicationService] = None
    _intent_classifier: Optional[IntentClassificationService] = None
    _ai_client = None  # singleton instructor-wrapped AI client
    _ai_model: Optional[str] = None  # model string for the AI client
    _gathering_service = None  # RequirementGatheringService singleton
    _lock: threading.Lock = threading.Lock()  # guards singleton initialization



    @classmethod
    def get_ai_client(cls):
        """Get or create the singleton instructor-wrapped AI client.

        Returns a ``(client, model)`` tuple.  The client is created once and
        reused across all services that need it.
        """
        if cls._ai_client is None:
            with cls._lock:
                if cls._ai_client is None:
                    from src.infrastructure.external_services.ai_client_factory import get_instructor_client
                    cls._ai_client, cls._ai_model = get_instructor_client()
        return cls._ai_client, cls._ai_model

    @classmethod
    def get_intent_classifier(cls) -> IntentClassificationService:
        """Get or create intent classifier."""
        if cls._intent_classifier is None:
            from src.infrastructure.external_services.ai_intent_classification import GeminiIntentClassificationService
            cls._intent_classifier = GeminiIntentClassificationService()
        return cls._intent_classifier

    @classmethod
    def get_gathering_service(cls):
        """Get or create the singleton RequirementGatheringService."""
        if cls._gathering_service is None:
            from src.application.services.requirement_gathering_service import RequirementGatheringService
            cls._gathering_service = RequirementGatheringService()
        return cls._gathering_service

    @classmethod
    def get_blueprint_generator(cls) -> BlueprintGeneratorService:
        """Get or create blueprint generator."""
        if cls._blueprint_generator is None:
            # Lazy import to avoid circular dependencies and external library requirements
            from src.infrastructure.external_services import GeminiAIBlueprintGenerator
            cls._blueprint_generator = GeminiAIBlueprintGenerator()
        return cls._blueprint_generator

    @classmethod
    def get_site_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Site repository."""
        from src.infrastructure.services.sharepoint.site_service import SiteService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.rest_api_client import RESTAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
        return SiteService(graph_client, rest_client)

    @classmethod
    def get_list_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create List repository."""
        from src.infrastructure.services.sharepoint.list_service import ListService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        return ListService(graph_client)
        
    @classmethod
    def get_page_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Page repository."""
        from src.infrastructure.services.sharepoint.page_service import PageService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.rest_api_client import RESTAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
        return PageService(rest_client, graph_client)
        
    @classmethod
    def get_library_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Library repository."""
        from src.infrastructure.services.sharepoint.library_service import LibraryService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        return LibraryService(graph_client)

    @classmethod
    def get_drive_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Drive repository for files and folders."""
        from src.infrastructure.services.sharepoint.drive_service import DriveService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        return DriveService(graph_client)

    @classmethod
    def get_enterprise_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Enterprise repository."""
        from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.rest_api_client import RESTAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        graph_client = GraphAPIClient(auth_service, target_site, user_token=user_token)
        rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
        return EnterpriseService(graph_client, rest_client)

    @classmethod
    def get_permission_repository(cls, user_token: Optional[str] = None, site_id: Optional[str] = None):
        """Get or create Permission repository."""
        from src.infrastructure.services.sharepoint.permission_service import PermissionService
        from src.infrastructure.services.rest_api_client import RESTAPIClient
        from src.infrastructure.services.authentication_service import AuthenticationService
        from src.infrastructure.config import settings
        
        target_site = site_id or settings.SITE_ID
        auth_service = AuthenticationService()
        rest_client = RESTAPIClient(auth_service, target_site, user_token=user_token)
        return PermissionService(rest_client)



    @classmethod
    def get_provisioning_service(cls) -> ProvisioningApplicationService:
        """Get or create provisioning application service."""
        if cls._provisioning_service is None:
            cls._provisioning_service = ProvisioningApplicationService(
                blueprint_generator=cls.get_blueprint_generator(),
                list_repository=cls.get_list_repository(),
                page_repository=cls.get_page_repository(),
                library_repository=cls.get_library_repository(),
                site_repository=cls.get_site_repository(),
                permission_repository=cls.get_permission_repository(),
                enterprise_repository=cls.get_enterprise_repository()
            )
        return cls._provisioning_service

    @classmethod
    def get_data_query_service(cls) -> DataQueryApplicationService:
        """Get or create data query application service."""
        if cls._data_query_service is None:
            # Lazy import to avoid circular dependencies
            from src.infrastructure.external_services.ai_data_query_service import AIDataQueryService
            from src.infrastructure.services.smart_resource_discovery import SmartResourceDiscoveryService
            site_repo = cls.get_site_repository()
            list_repo = cls.get_list_repository()
            page_repo = cls.get_page_repository()
            library_repo = cls.get_library_repository()
            drive_repo = cls.get_drive_repository()
            
            from src.infrastructure.config import settings
            site_id = getattr(site_repo, 'site_id', settings.SITE_ID)

            # Resolve the singleton AI client once so both services share it.
            ai_client, ai_model = cls.get_ai_client()

            # Build SmartResourceDiscoveryService with the AI client injected
            # directly — no post-construction back-fill needed.
            smart_discovery = SmartResourceDiscoveryService(
                site_repository=site_repo,
                list_repository=list_repo,
                library_repository=library_repo,
                page_repository=page_repo,
                ai_client=ai_client,
                ai_model=ai_model,
            )

            data_query_service = AIDataQueryService(
                site_repository=site_repo,
                list_repository=list_repo,
                library_repository=library_repo,
                page_repository=page_repo,
                drive_repository=drive_repo,
                graph_client=getattr(site_repo, 'graph_client', None),
                site_id=site_id,
                smart_discovery_service=smart_discovery,
                ai_client=ai_client,
                ai_model=ai_model,
            )

            cls._data_query_service = DataQueryApplicationService(data_query_service)
        return cls._data_query_service
    
    @classmethod
    def set_blueprint_generator(cls, generator: BlueprintGeneratorService) -> None:
        """Set blueprint generator (useful for testing)."""
        cls._blueprint_generator = generator
    

    
    @classmethod
    def set_provisioning_service(cls, service: ProvisioningApplicationService) -> None:
        """Set provisioning service (useful for testing)."""
        cls._provisioning_service = service

    @classmethod
    def reset(cls):
        """Reset all services (useful for testing)."""
        cls._blueprint_generator = None
        cls._provisioning_service = None
        cls._data_query_service = None
        cls._intent_classifier = None
        cls._ai_client = None
        cls._ai_model = None
        cls._gathering_service = None


def get_provisioning_service() -> ProvisioningApplicationService:
    """FastAPI dependency provider for provisioning service."""
    return ServiceContainer.get_provisioning_service()


def get_data_query_service() -> DataQueryApplicationService:
    """FastAPI dependency provider for data query service."""
    return ServiceContainer.get_data_query_service()


def get_intent_classifier() -> IntentClassificationService:
    """FastAPI dependency provider for intent classifier."""
    return ServiceContainer.get_intent_classifier()


def get_site_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_site_repository(user_token=user_token, site_id=site_id)

def get_list_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_list_repository(user_token=user_token, site_id=site_id)

def get_page_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_page_repository(user_token=user_token, site_id=site_id)

def get_library_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_library_repository(user_token=user_token, site_id=site_id)

def get_drive_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_drive_repository(user_token=user_token, site_id=site_id)

def get_permission_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_permission_repository(user_token=user_token, site_id=site_id)

def get_enterprise_repository(user_token: Optional[str] = None, site_id: Optional[str] = None):
    return ServiceContainer.get_enterprise_repository(user_token=user_token, site_id=site_id)



