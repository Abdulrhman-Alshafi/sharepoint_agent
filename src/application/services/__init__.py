"""Application services - orchestrate use cases and coordinate with repositories."""

from src.domain.services import BlueprintGeneratorService, DataQueryService
from src.application.use_cases import QueryDataUseCase
from src.application.use_cases.provision_resources_use_case import ProvisionResourcesUseCase
from src.application.commands import ProvisionResourcesCommand, DataQueryCommand
from src.application.dtos import ProvisionResourcesResponseDTO, DataQueryResponseDTO


class ProvisioningApplicationService:
    """Application service for provisioning operations."""

    def __init__(
        self,
        blueprint_generator: BlueprintGeneratorService,
        list_repository=None,
        page_repository=None,
        library_repository=None,
        site_repository=None,
        permission_repository=None,
        enterprise_repository=None
    ):
        self.usecase = ProvisionResourcesUseCase(
            blueprint_generator,
            list_repository=list_repository,
            page_repository=page_repository,
            library_repository=library_repository,
            site_repository=site_repository,
            permission_repository=permission_repository,
            enterprise_repository=enterprise_repository
        )

    async def provision_resources(self, prompt: str, skip_high_risk_check: bool = False, skip_collision_check: bool = False, user_email: str = "", user_login_name: str = "", target_site_id: str = "", user_token: str = "") -> ProvisionResourcesResponseDTO:
        """Orchestrate the provisioning of resources.
        
        Args:
            prompt: User's provisioning request
            skip_high_risk_check: If True, bypass high-risk validation (user already confirmed)
            skip_collision_check: If True, skip auto-conversion of CREATE to UPDATE on name collision
            user_email: Optional email of the user
            user_login_name: Optional login name of the user
            target_site_id: Optional target site ID to provision resources
            user_token: Optional raw bearer token for OBO authentication in permission checks
        """
        command = ProvisionResourcesCommand(prompt=prompt, user_email=user_email, user_login_name=user_login_name, target_site_id=target_site_id)
        return await self.usecase.execute(command, skip_high_risk_check=skip_high_risk_check, skip_collision_check=skip_collision_check, user_token=user_token)


class DataQueryApplicationService:
    """Application service for data intelligence operations."""

    def __init__(self, data_query_service: DataQueryService, permission_repository=None):
        self.usecase = QueryDataUseCase(data_query_service, permission_repository=permission_repository)

    async def query_data(self, question: str, site_ids=None, page_id=None, page_url=None, page_title=None, context_site_id=None, user_login_name: str = "") -> DataQueryResponseDTO:
        """Orchestrate data query usecase."""
        command = DataQueryCommand(
            question=question,
            site_ids=site_ids,
            page_id=page_id,
            page_url=page_url,
            page_title=page_title,
            context_site_id=context_site_id,
            user_login_name=user_login_name,
        )
        return await self.usecase.execute(command)
