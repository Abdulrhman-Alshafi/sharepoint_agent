"""Tests for BlueprintConverter."""

import pytest

from src.application.converters import BlueprintConverter
from src.domain.entities.core import (
    ProvisioningBlueprint, SPList, SPPage, ActionType, ProvisioningBlueprint
)
from src.domain.value_objects import SPColumn
from src.application.dtos import BlueprintDTO


def _empty_blueprint():
    from src.domain.entities.core import SPSite
    return ProvisioningBlueprint(
        reasoning="build it",
        lists=[],
        pages=[],
        custom_components=[],
        document_libraries=[],
        groups=[],
        sites=[SPSite(title="Default", description="", action=ActionType.CREATE)],
        term_sets=[],
        content_types=[],
        views=[],
        workflows=[],
    )


class TestBlueprintConverter:
    def test_to_dto_returns_blueprint_dto(self):
        dto = BlueprintConverter.to_dto(_empty_blueprint())
        assert isinstance(dto, BlueprintDTO)

    def test_to_dto_preserves_reasoning(self):
        bp = _empty_blueprint()
        bp.reasoning = "custom reasoning"
        dto = BlueprintConverter.to_dto(bp)
        assert dto.reasoning == "custom reasoning"

    def test_to_dto_converts_list(self):
        col = SPColumn(name="Status", type="choice", required=False, choices=["Open", "Done"])
        sp_list = SPList(title="Tasks", description="Task list", columns=[col], action=ActionType.CREATE)
        bp = _empty_blueprint()
        bp.lists = [sp_list]
        dto = BlueprintConverter.to_dto(bp)
        assert len(dto.lists) == 1
        assert dto.lists[0].title == "Tasks"
        assert len(dto.lists[0].columns) == 1
        assert dto.lists[0].columns[0].name == "Status"

    def test_to_dto_converts_page(self):
        from src.domain.value_objects import WebPart
        sp_page = SPPage(
            title="Home",
            webparts=[WebPart(type="text", properties={})],
            action=ActionType.CREATE,
        )
        bp = _empty_blueprint()
        bp.pages = [sp_page]
        dto = BlueprintConverter.to_dto(bp)
        assert len(dto.pages) == 1
        assert dto.pages[0].title == "Home"

    def test_to_dto_empty_collections(self):
        dto = BlueprintConverter.to_dto(_empty_blueprint())
        assert dto.lists == []
        assert dto.pages == []
        assert dto.document_libraries == []
        assert dto.groups == []
