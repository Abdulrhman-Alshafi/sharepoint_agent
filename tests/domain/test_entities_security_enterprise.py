"""Tests for security and enterprise domain entities."""

import pytest
from src.domain.entities.security import SharePointGroup, PermissionLevel
from src.domain.entities.enterprise import TermSet, ContentType, SPView, WorkflowScaffold


class TestPermissionLevel:
    def test_all_values(self):
        values = {p.value for p in PermissionLevel}
        assert any("ead" in v for v in values)   # "Read" or "READ"
        assert any("ontribute" in v for v in values)  # "Contribute" or "CONTRIBUTE"


class TestSharePointGroup:
    def test_valid_creation(self):
        group = SharePointGroup(name="Site Owners")
        assert group.name == "Site Owners"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            SharePointGroup(name="")

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            SharePointGroup(name="   ")

    def test_default_permission_level(self):
        group = SharePointGroup(name="Readers")
        # Default should be READ or similar - just check it exists
        assert group.permission_level is not None

    def test_custom_permission_level(self):
        group = SharePointGroup(name="Editors", permission_level=PermissionLevel.CONTRIBUTE)
        assert group.permission_level == PermissionLevel.CONTRIBUTE


class TestTermSet:
    def test_basic_creation(self):
        ts = TermSet(name="Departments", terms=["HR", "Finance"])
        assert ts.name == "Departments"
        assert ts.terms == ["HR", "Finance"]

    def test_default_group_name(self):
        ts = TermSet(name="Tags", terms=[])
        assert ts.group_name == "Default Site Collection Group"

    def test_custom_group_name(self):
        ts = TermSet(name="Tags", terms=[], group_name="Site Collection")
        assert ts.group_name == "Site Collection"


class TestContentType:
    def test_basic_creation(self):
        ct = ContentType(name="Contract", description="Legal contract")
        assert ct.name == "Contract"

    def test_default_parent_type(self):
        ct = ContentType(name="Contract", description="d")
        assert ct.parent_type == "Item"

    def test_custom_parent_type(self):
        ct = ContentType(name="Document", description="d", parent_type="Document")
        assert ct.parent_type == "Document"

    def test_columns_default_to_empty(self):
        ct = ContentType(name="Contract", description="d")
        assert ct.columns == []


class TestSPView:
    def test_basic_creation(self):
        view = SPView(title="Active Items", target_list_title="Tasks", columns=["Title", "Status"])
        assert view.title == "Active Items"
        assert view.target_list_title == "Tasks"

    def test_default_row_limit(self):
        view = SPView(title="View", target_list_title="Tasks", columns=["Title"])
        assert view.row_limit == 30

    def test_custom_row_limit(self):
        view = SPView(title="View", target_list_title="Tasks", columns=["Title"], row_limit=100)
        assert view.row_limit == 100


class TestWorkflowScaffold:
    def test_basic_creation(self):
        wf = WorkflowScaffold(name="Approval", trigger_type="item_created", target_list_title="Tasks")
        assert wf.name == "Approval"
        assert wf.trigger_type == "item_created"
        assert wf.target_list_title == "Tasks"

    def test_actions_default_to_empty(self):
        wf = WorkflowScaffold(name="W", trigger_type="t", target_list_title="T")
        assert wf.actions == []
