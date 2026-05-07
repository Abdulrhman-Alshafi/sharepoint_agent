"""Tests for PayloadBuilders utility class."""

import pytest
from src.infrastructure.repositories.utils.payload_builders import PayloadBuilders
from src.domain.value_objects import SPColumn
from src.domain.entities.core import SPList, SPPage, ActionType
from src.domain.value_objects import WebPart
from src.domain.entities.document import DocumentLibrary
from src.domain.entities.security import SharePointGroup, PermissionLevel
from src.domain.entities.enterprise import ContentType, TermSet, SPView


class TestBuildListPayload:
    def test_delegates_to_entity(self):
        col = SPColumn(name="Status", type="text", required=False)
        sp_list = SPList(title="Tasks", description="Task list", columns=[col])
        payload = PayloadBuilders.build_list_payload(sp_list)
        assert payload["displayName"] == "Tasks"
        assert payload["description"] == "Task list"


class TestBuildPagePayload:
    def test_delegates_to_entity(self):
        wp = WebPart(type="text", properties={"content": "Hello"})
        page = SPPage(title="Home Page", webparts=[wp])
        payload = PayloadBuilders.build_page_payload(page)
        assert payload["title"] == "Home Page"


class TestBuildLibraryPayload:
    def test_delegates_to_entity(self):
        lib = DocumentLibrary(title="Contracts", description="Legal docs")
        payload = PayloadBuilders.build_library_payload(lib)
        assert payload["displayName"] == "Contracts"
        assert payload["list"]["template"] == "documentLibrary"


class TestBuildColumnPayload:
    @pytest.mark.parametrize("col_type,expected_key", [
        ("text", "text"),
        ("note", "text"),
        ("number", "number"),
        ("dateTime", "dateTime"),
        ("boolean", "boolean"),
        ("lookup", "lookup"),
        ("managed_metadata", "term"),
        ("currency", "currency"),
        ("personOrGroup", "personOrGroup"),
        ("hyperlinkOrPicture", "hyperlinkOrPicture"),
        ("geolocation", "geolocation"),
    ])
    def test_type_mapping(self, col_type, expected_key):
        col = SPColumn(name="Col", type=col_type, required=False)
        payload = PayloadBuilders.build_column_payload(col)
        assert expected_key in payload

    def test_unknown_type_falls_back_to_text(self):
        col = SPColumn(name="Custom", type="text", required=False)
        # Manually override type for testing
        import dataclasses
        bad_col = dataclasses.replace(col)
        # Create a simple mock with unknown type
        class FakeCol:
            name = "Col"
            required = False
            type = "unknown_type"
            choices = []
        payload = PayloadBuilders.build_column_payload(FakeCol())
        assert "text" in payload

    def test_choice_column_with_choices(self):
        col = SPColumn(name="Status", type="choice", required=False, choices=["Active", "Closed"])
        payload = PayloadBuilders.build_column_payload(col)
        assert "choice" in payload
        # choices should be present
        choice_val = payload["choice"]
        if isinstance(choice_val, dict):
            assert choice_val.get("choices") == ["Active", "Closed"]

    def test_column_name_preserved(self):
        col = SPColumn(name="MyColumn", type="text", required=True)
        payload = PayloadBuilders.build_column_payload(col)
        assert payload["name"] == "MyColumn"

    def test_required_flag_preserved(self):
        col = SPColumn(name="Status", type="text", required=True)
        payload = PayloadBuilders.build_column_payload(col)
        assert payload["required"] is True


class TestBuildGroupPayload:
    def test_basic_structure(self):
        group = SharePointGroup(name="Site Members")
        payload = PayloadBuilders.build_group_payload(group)
        assert payload["Title"] == "Site Members"
        assert "__metadata" in payload
        assert payload["__metadata"]["type"] == "SP.Group"

    def test_description_present(self):
        group = SharePointGroup(name="Site Members", description="Members group")
        payload = PayloadBuilders.build_group_payload(group)
        assert payload["Description"] == "Members group"

    def test_default_description_fallback(self):
        group = SharePointGroup(name="Viewers", description="")
        payload = PayloadBuilders.build_group_payload(group)
        # Falls back to "{name} SharePoint Group"
        assert "Viewers" in payload["Description"]


class TestBuildContentTypePayload:
    def test_basic_structure(self):
        ct = ContentType(name="Contract", description="Legal contract", parent_type="Item")
        payload = PayloadBuilders.build_content_type_payload(ct)
        assert payload["name"] == "Contract"
        assert payload["description"] == "Legal contract"
        assert payload["base"]["name"] == "Item"


class TestBuildTermSetPayload:
    def test_basic_structure(self):
        ts = TermSet(name="Departments", terms=["HR", "Finance"])
        payload = PayloadBuilders.build_term_set_payload(ts)
        assert payload is not None
        # Should include the term set name
        assert "Departments" in str(payload)


class TestBuildViewPayload:
    def test_basic_structure(self):
        view = SPView(title="Active Items", target_list_title="Tasks", columns=["Title", "Status"])
        payload = PayloadBuilders.build_view_payload(view)
        assert payload is not None
