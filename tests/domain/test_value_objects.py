"""Tests for value objects: SPColumn, WebPart, ColumnMapping."""

import pytest
from dataclasses import FrozenInstanceError
from src.domain.value_objects import SPColumn, WebPart, ColumnMapping


class TestSPColumn:
    def test_valid_creation(self):
        col = SPColumn(name="Status", type="text", required=True)
        assert col.name == "Status"
        assert col.type == "text"
        assert col.required is True

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            SPColumn(name="", type="text", required=False)

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            SPColumn(name="  ", type="text", required=False)

    def test_frozen_immutable(self):
        col = SPColumn(name="Status", type="text", required=False)
        with pytest.raises((FrozenInstanceError, TypeError)):
            col.name = "Changed"  # type: ignore

    def test_choices_default_to_empty_list(self):
        col = SPColumn(name="Status", type="choice", required=False)
        assert col.choices == []

    def test_choices_stored(self):
        col = SPColumn(name="Status", type="choice", required=False, choices=["Active", "Done"])
        assert col.choices == ["Active", "Done"]

    def test_lookup_list_optional(self):
        col = SPColumn(name="Ref", type="lookup", required=False)
        assert col.lookup_list is None

    def test_lookup_list_stored(self):
        col = SPColumn(name="Ref", type="lookup", required=False, lookup_list="Tasks")
        assert col.lookup_list == "Tasks"

    def test_term_set_id_optional(self):
        col = SPColumn(name="Tags", type="managed_metadata", required=False)
        assert col.term_set_id is None

    def test_term_set_id_stored(self):
        col = SPColumn(name="Tags", type="managed_metadata", required=False, term_set_id="abc-123")
        assert col.term_set_id == "abc-123"

    @pytest.mark.parametrize("col_type", [
        "text", "note", "number", "dateTime", "choice", "lookup",
        "managed_metadata", "boolean", "currency", "personOrGroup",
        "hyperlinkOrPicture", "geolocation",
    ])
    def test_all_valid_types_accepted(self, col_type):
        col = SPColumn(name="Col", type=col_type, required=False)
        assert col.type == col_type


class TestWebPart:
    def test_valid_creation(self):
        wp = WebPart(type="text", properties={"content": "Hello"})
        assert wp.type == "text"
        assert wp.properties == {"content": "Hello"}

    def test_empty_type_raises(self):
        with pytest.raises(ValueError, match="type cannot be empty"):
            WebPart(type="", properties={})

    def test_whitespace_type_raises(self):
        with pytest.raises(ValueError, match="type cannot be empty"):
            WebPart(type="  ", properties={})

    def test_frozen_immutable(self):
        wp = WebPart(type="text", properties={})
        with pytest.raises((FrozenInstanceError, TypeError)):
            wp.type = "changed"  # type: ignore

    def test_id_defaults_to_none(self):
        wp = WebPart(type="text", properties={})
        assert wp.id is None

    def test_id_stored(self):
        wp = WebPart(type="text", properties={}, id="guid-123")
        assert wp.id == "guid-123"

    def test_empty_properties_dict_accepted(self):
        wp = WebPart(type="NewsWebPart", properties={})
        assert wp.properties == {}


class TestColumnMapping:
    def test_basic_creation(self):
        cm = ColumnMapping(column_type="text", graph_api_schema={"text": {}})
        assert cm.column_type == "text"
        assert cm.graph_api_schema == {"text": {}}
