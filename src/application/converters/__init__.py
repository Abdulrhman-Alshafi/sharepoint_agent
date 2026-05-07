"""Blueprint converter utilities."""

from typing import List
from src.domain.entities import (
    ProvisioningBlueprint, SPList, SPPage, CustomWebPartCode,
    DocumentLibrary, SharePointGroup, TermSet, ContentType, SPView, WorkflowScaffold
)
from src.application.dtos import (
    BlueprintDTO, ListDTO, PageDTO, ColumnDTO, WebPartDTO,
    CustomWebPartCodeDTO, DocumentLibraryDTO, SharePointGroupDTO,
    TermSetDTO, ContentTypeDTO, SPViewDTO, WorkflowScaffoldDTO
)


class BlueprintConverter:
    """Converts domain blueprint entities to DTOs."""

    @staticmethod
    def to_dto(blueprint: ProvisioningBlueprint) -> BlueprintDTO:
        """Convert ProvisioningBlueprint entity to BlueprintDTO.
        
        Args:
            blueprint: Domain blueprint entity
            
        Returns:
            DTO representation of blueprint
        """
        return BlueprintDTO(
            reasoning=blueprint.reasoning,
            lists=BlueprintConverter._convert_lists(blueprint.lists),
            pages=BlueprintConverter._convert_pages(blueprint.pages),
            custom_components=BlueprintConverter._convert_custom_components(blueprint.custom_components),
            document_libraries=BlueprintConverter._convert_document_libraries(blueprint.document_libraries),
            groups=BlueprintConverter._convert_groups(blueprint.groups),
            term_sets=BlueprintConverter._convert_term_sets(blueprint.term_sets),
            content_types=BlueprintConverter._convert_content_types(blueprint.content_types),
            views=BlueprintConverter._convert_views(blueprint.views),
            workflows=BlueprintConverter._convert_workflows(blueprint.workflows),
        )

    @staticmethod
    def _convert_lists(lists: List[SPList]) -> List[ListDTO]:
        """Convert list entities to DTOs."""
        return [
            ListDTO(
                title=lst.title,
                description=lst.description,
                columns=[
                    ColumnDTO(
                        name=col.name,
                        type=col.type,
                        required=col.required,
                        choices=getattr(col, "choices", []),
                        lookup_list=getattr(col, "lookup_list", ""),
                        term_set_id=getattr(col, "term_set_id", "")
                    )
                    for col in lst.columns
                ],
                content_types=lst.content_types,
                seed_data=lst.seed_data,
                action=lst.action.value
            )
            for lst in lists
        ]

    @staticmethod
    def _convert_pages(pages: List[SPPage]) -> List[PageDTO]:
        """Convert page entities to DTOs."""
        return [
            PageDTO(
                title=pg.title,
                webparts=[
                    WebPartDTO(type=wp.type, properties=wp.properties)
                    for wp in pg.webparts
                ],
                action=pg.action.value
            )
            for pg in pages
        ]

    @staticmethod
    def _convert_custom_components(components: List[CustomWebPartCode]) -> List[CustomWebPartCodeDTO]:
        """Convert custom component entities to DTOs."""
        return [
            CustomWebPartCodeDTO(
                component_name=c.component_name,
                tsx_content=c.tsx_content,
                scss_content=c.scss_content
            )
            for c in components
        ]

    @staticmethod
    def _convert_document_libraries(libraries: List[DocumentLibrary]) -> List[DocumentLibraryDTO]:
        """Convert document library entities to DTOs."""
        return [
            DocumentLibraryDTO(
                title=lib.title,
                description=lib.description,
                content_types=lib.content_types,
                seed_data=lib.seed_data,
                action=lib.action.value
            )
            for lib in libraries
        ]

    @staticmethod
    def _convert_groups(groups: List[SharePointGroup]) -> List[SharePointGroupDTO]:
        """Convert SharePoint group entities to DTOs."""
        return [
            SharePointGroupDTO(
                name=g.name,
                description=g.description,
                permission_level=g.permission_level.value,
                target_library_title=g.target_library_title,
                action=g.action.value
            )
            for g in groups
        ]

    @staticmethod
    def _convert_term_sets(term_sets: List[TermSet]) -> List[TermSetDTO]:
        """Convert term set entities to DTOs."""
        return [
            TermSetDTO(
                name=ts.name,
                terms=ts.terms,
                group_name=ts.group_name,
                action=ts.action.value
            )
            for ts in term_sets
        ]

    @staticmethod
    def _convert_content_types(content_types: List[ContentType]) -> List[ContentTypeDTO]:
        """Convert content type entities to DTOs."""
        return [
            ContentTypeDTO(
                name=ct.name,
                description=ct.description,
                parent_type=ct.parent_type,
                columns=ct.columns,
                action=ct.action.value
            )
            for ct in content_types
        ]

    @staticmethod
    def _convert_views(views: List[SPView]) -> List[SPViewDTO]:
        """Convert view entities to DTOs."""
        return [
            SPViewDTO(
                title=v.title,
                target_list_title=v.target_list_title,
                columns=v.columns,
                row_limit=v.row_limit,
                query=v.query,
                action=v.action.value
            )
            for v in views
        ]

    @staticmethod
    def _convert_workflows(workflows: List[WorkflowScaffold]) -> List[WorkflowScaffoldDTO]:
        """Convert workflow entities to DTOs."""
        return [
            WorkflowScaffoldDTO(
                name=w.name,
                trigger_type=w.trigger_type,
                target_list_title=w.target_list_title,
                actions=w.actions,
                action=w.action.value
            )
            for w in workflows
        ]
