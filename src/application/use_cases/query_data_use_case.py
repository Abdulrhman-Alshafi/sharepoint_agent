"""Query data use case."""

from typing import Optional

from src.domain.services import DataQueryService
from src.domain.entities.core import SPPermissionMask
from src.domain.exceptions import PermissionDeniedException
from src.domain.repositories.permission_repository import IPermissionRepository
from src.application.commands import DataQueryCommand
from src.application.dtos import DataQueryResponseDTO


class QueryDataUseCase:
    """Use case for querying data intelligence (RAG)."""

    def __init__(self, data_query_service: DataQueryService, permission_repository: Optional[IPermissionRepository] = None):
        self.data_query_service = data_query_service
        self.permission_repository = permission_repository

    async def execute(self, command: DataQueryCommand) -> DataQueryResponseDTO:
        user_login = command.user_login_name
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to query SharePoint data.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to query SharePoint data.")
        result = await self.data_query_service.answer_question(
            command.question,
            site_ids=command.site_ids,
            page_id=command.page_id,
            page_url=command.page_url,
            page_title=command.page_title,
            context_site_id=command.context_site_id,
        )
        return DataQueryResponseDTO(
            answer=result.answer,
            data_summary=result.data_summary,
            source_list=result.source_list,
            resource_link=result.resource_link,
            suggested_actions=result.suggested_actions,
            source_site_name=result.source_site_name,
            source_site_url=result.source_site_url,
            source_resource_type=result.source_resource_type,
            sources=[s.__dict__ for s in result.sources] if result.sources else [],
            clarification_candidates=result.clarification_candidates,
        )
