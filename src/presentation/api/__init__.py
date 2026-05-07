"""Dependency injection and providers for API endpoints."""

import threading
from typing import Callable, Optional
from src.domain.services import BlueprintGeneratorService, DataQueryService
from src.domain.services.intent_classification import IntentClassificationService
from src.domain.repositories import SharePointRepository
from src.application.services import ProvisioningApplicationService, DataQueryApplicationService


class ServiceContainer:
    """Container for application services and dependencies."""
    
    _blueprint_generator: Optional[BlueprintGeneratorService] = None
    _sharepoint_repository: Optional[SharePointRepository] = None
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
    def get_sharepoint_repository(cls) -> SharePointRepository:
        """Get or create SharePoint repository."""
        if cls._sharepoint_repository is None:
            with cls._lock:
                if cls._sharepoint_repository is None:
                    from src.infrastructure.repositories import GraphAPISharePointRepository
                    cls._sharepoint_repository = GraphAPISharePointRepository()
        return cls._sharepoint_repository

    @classmethod
    def get_provisioning_service(cls) -> ProvisioningApplicationService:
        """Get or create provisioning application service."""
        if cls._provisioning_service is None:
            cls._provisioning_service = ProvisioningApplicationService(
                blueprint_generator=cls.get_blueprint_generator(),
                sharepoint_repository=cls.get_sharepoint_repository()
            )
        return cls._provisioning_service

    @classmethod
    def get_data_query_service(cls) -> DataQueryApplicationService:
        """Get or create data query application service."""
        if cls._data_query_service is None:
            # Lazy import to avoid circular dependencies
            from src.infrastructure.external_services.ai_data_query_service import AIDataQueryService
            from src.infrastructure.services.smart_resource_discovery import SmartResourceDiscoveryService
            repo = cls.get_sharepoint_repository()
            
            # Extract graph client from repo if possible
            graph_client = getattr(repo, 'graph_client', None)
            
            from src.infrastructure.config import settings
            site_id = getattr(repo, 'site_id', settings.SITE_ID)



            # Resolve the singleton AI client once so both services share it.
            ai_client, ai_model = cls.get_ai_client()

            # Build SmartResourceDiscoveryService with the AI client injected
            # directly — no post-construction back-fill needed.
            smart_discovery = SmartResourceDiscoveryService(
                sharepoint_repository=repo,
                ai_client=ai_client,
                ai_model=ai_model,
            )

            data_query_service = AIDataQueryService(
                repo, graph_client, site_id,
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
    def set_sharepoint_repository(cls, repository: SharePointRepository) -> None:
        """Set SharePoint repository (useful for testing)."""
        cls._sharepoint_repository = repository
    
    @classmethod
    def set_provisioning_service(cls, service: ProvisioningApplicationService) -> None:
        """Set provisioning service (useful for testing)."""
        cls._provisioning_service = service

    @classmethod
    def reset(cls):
        """Reset all services (useful for testing)."""
        cls._blueprint_generator = None
        cls._sharepoint_repository = None
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


def get_repository(user_token: Optional[str] = None, site_id: Optional[str] = None) -> SharePointRepository:
    """FastAPI dependency provider for SharePoint repository.

    When *user_token* is provided a fresh per-request repository is created so
    that all Graph calls are made on-behalf-of the signed-in user (OBO flow).
    When no token is provided the module-level singleton (service account) is
    returned — used by background indexing, provisioning, etc.
    """
    if user_token:
        from src.infrastructure.repositories import GraphAPISharePointRepository
        return GraphAPISharePointRepository(user_token=user_token, site_id=site_id)
    return ServiceContainer.get_sharepoint_repository()
    @classmethod
    async def get_graph_client(cls):
        from src.infrastructure.services.graph_api_client import GraphAPIClient
        from src.infrastructure.services.cache_service import CacheService
        # Using placeholder CacheService where applicable
        return GraphAPIClient(CacheService())
