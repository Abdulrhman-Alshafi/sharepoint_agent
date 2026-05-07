"""Domain services - contain business logic and use domain models."""

from abc import ABC, abstractmethod
from src.domain.entities import ProvisioningBlueprint, DataQueryResult, PromptValidationResult
from src.domain.services.intent_classification import IntentClassificationService
from src.domain.services.smart_resource_discovery import ISmartResourceDiscoveryService


class BlueprintGeneratorService(ABC):
    """Domain service for generating provisioning blueprints from prompts."""

    @abstractmethod
    async def validate_prompt(self, prompt: str) -> PromptValidationResult:
        """Validate a user prompt before generating a blueprint."""
        pass

    @abstractmethod
    async def generate_blueprint(self, prompt: str, tenant_users: list = None) -> ProvisioningBlueprint:
        """Generate a provisioning blueprint from a user prompt.
        
        Args:
            prompt: User's provisioning request
            tenant_users: Optional list of real tenant user dicts for person columns
        """
        pass


class DataQueryService(ABC):
    """Domain service for answering data intelligence questions over SharePoint."""

    @abstractmethod
    async def answer_question(
        self, question: str, site_ids=None
    ) -> DataQueryResult:
        """Answer a user question by reasoning over SharePoint list data (RAG).

        Args:
            question: Natural-language question from the user.
            site_ids: Optional list of SP site IDs to scope the search.
                      If None the service decides which sites to use.
        """
        pass
