"""Tests for core domain entities: SPSite, SPList, SPPage, CustomWebPartCode, ProvisioningBlueprint."""

import pytest
from src.domain.entities.core import (
    ActionType,
    SPPermissionMask,
    SPSite,
    SPList,
    SPPage,
    CustomWebPartCode,
    ProvisioningBlueprint,
)
from src.domain.value_objects import SPColumn, WebPart
from src.domain.entities.document import DocumentLibrary
from src.domain.entities.security import SharePointGroup


# ---------------------------------------------------------------------------
# ActionType
# ---------------------------------------------------------------------------

class TestActionType:
    def test_all_values(self):
        assert ActionType.CREATE == "CREATE"
        assert ActionType.UPDATE == "UPDATE"
        assert ActionType.DELETE == "DELETE"

    def test_string_coercion(self):
        assert ActionType("CREATE") is ActionType.CREATE


# ---------------------------------------------------------------------------
# SPPermissionMask
# ---------------------------------------------------------------------------

class TestSPPermissionMask:
    def test_all_values(self):
        expected = {
            "ViewListItems", "AddListItems", "EditListItems",
            "DeleteListItems", "ManageLists", "ManageWeb", "FullMask",
        }
        actual = {m.value for m in SPPermissionMask}
        assert actual == expected


# ---------------------------------------------------------------------------
# SPSite
# ---------------------------------------------------------------------------

class TestSPSite:
    def _col(self):
        return SPColumn(name="Status", type="text", required=False)

    def test_valid_sts_site(self):
        site = SPSite(title="My Site", description="desc", template="sts")
        assert site.title == "My Site"
        assert site.template == "sts"

    def test_valid_communication_site(self):
        site = SPSite(title="Comms", description="d", template="sitepagepublishing")
        assert site.template == "sitepagepublishing"

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPSite(title="", description="d")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPSite(title="   ", description="d")

    def test_invalid_template_raises(self):
        with pytest.raises(ValueError, match="template must be"):
            SPSite(title="T", description="d", template="community")

    def test_default_template_is_sts(self):
        site = SPSite(title="T", description="d")
        assert site.template == "sts"


# ---------------------------------------------------------------------------
# SPList
# ---------------------------------------------------------------------------

class TestSPList:
    def _col(self, name="Status", col_type="text", required=False):
        return SPColumn(name=name, type=col_type, required=required)

    def test_valid_list(self):
        sp_list = SPList(title="Tasks", description="d", columns=[self._col()])
        assert sp_list.title == "Tasks"

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPList(title="", description="d", columns=[self._col()])

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPList(title="  ", description="d", columns=[self._col()])

    def test_empty_columns_on_create_raises(self):
        with pytest.raises(ValueError, match="at least one column"):
            SPList(title="T", description="d", columns=[], action=ActionType.CREATE)

    def test_empty_columns_on_delete_is_valid(self):
        sp_list = SPList(title="T", description="d", columns=[], action=ActionType.DELETE)
        assert sp_list.action == ActionType.DELETE

    def test_empty_columns_on_update_raises(self):
        with pytest.raises(ValueError, match="at least one column"):
            SPList(title="T", description="d", columns=[], action=ActionType.UPDATE)

    def test_get_required_columns_filters_correctly(self):
        cols = [
            self._col("Title", required=True),
            self._col("Notes", required=False),
            self._col("Owner", required=True),
        ]
        sp_list = SPList(title="T", description="d", columns=cols)
        required = sp_list.get_required_columns()
        assert len(required) == 2
        assert all(c.required for c in required)

    def test_get_required_columns_empty_when_none_required(self):
        cols = [self._col("A", required=False), self._col("B", required=False)]
        sp_list = SPList(title="T", description="d", columns=cols)
        assert sp_list.get_required_columns() == []

    def test_to_graph_api_payload_title_column_skipped(self):
        cols = [
            SPColumn(name="Title", type="text", required=True),
            SPColumn(name="Status", type="choice", required=False, choices=["Active", "Done"]),
        ]
        sp_list = SPList(title="My List", description="desc", columns=cols)
        payload = sp_list.to_graph_api_payload()
        col_names = [c["name"] for c in payload["columns"]]
        assert "Title" not in col_names
        assert "Status" in col_names

    def test_to_graph_api_payload_structure(self):
        cols = [self._col("Status")]
        sp_list = SPList(title="My List", description="A list", columns=cols)
        payload = sp_list.to_graph_api_payload()
        assert payload["displayName"] == "My List"
        assert payload["description"] == "A list"
        assert payload["list"]["template"] == "genericList"

    def test_to_graph_api_payload_custom_template(self):
        cols = [self._col("Status")]
        sp_list = SPList(title="T", description="d", columns=cols, template="tasks")
        payload = sp_list.to_graph_api_payload()
        assert payload["list"]["template"] == "tasks"

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
    def test_to_graph_api_payload_type_mapping(self, col_type, expected_key):
        cols = [SPColumn(name="Col", type=col_type, required=False)]
        sp_list = SPList(title="T", description="d", columns=cols)
        payload = sp_list.to_graph_api_payload()
        col = payload["columns"][0]
        assert expected_key in col

    def test_to_graph_api_payload_choice_with_choices(self):
        cols = [SPColumn(name="Status", type="choice", required=False, choices=["A", "B"])]
        sp_list = SPList(title="T", description="d", columns=cols)
        payload = sp_list.to_graph_api_payload()
        col = payload["columns"][0]
        assert "choice" in col
        assert col["choice"].get("choices") == ["A", "B"]


# ---------------------------------------------------------------------------
# SPPage
# ---------------------------------------------------------------------------

class TestSPPage:
    def _wp(self, wp_type="text"):
        return WebPart(type=wp_type, properties={"content": "Hello"})

    def test_valid_page(self):
        page = SPPage(title="Home", webparts=[self._wp()])
        assert page.title == "Home"

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPPage(title="", webparts=[self._wp()])

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            SPPage(title="  ", webparts=[self._wp()])

    def test_empty_webparts_on_create_raises(self):
        with pytest.raises(ValueError, match="at least one web part"):
            SPPage(title="T", webparts=[], action=ActionType.CREATE)

    def test_empty_webparts_on_delete_valid(self):
        page = SPPage(title="T", webparts=[], action=ActionType.DELETE)
        assert page.action == ActionType.DELETE

    def test_to_graph_api_payload_text_webpart(self):
        wp = WebPart(type="text", properties={"content": "Hello World"})
        page = SPPage(title="My Page", webparts=[wp])
        payload = page.to_graph_api_payload()
        assert payload["title"] == "My Page"
        sections = payload["canvasLayout"]["horizontalSections"]
        webparts = sections[0]["columns"][0]["webparts"]
        assert webparts[0]["type"] == "rte"
        assert webparts[0]["innerHtml"] == "Hello World"

    def test_to_graph_api_payload_rte_webpart(self):
        wp = WebPart(type="rte", properties={"content": "Rich text"})
        page = SPPage(title="P", webparts=[wp])
        payload = page.to_graph_api_payload()
        webparts = payload["canvasLayout"]["horizontalSections"][0]["columns"][0]["webparts"]
        assert webparts[0]["type"] == "rte"

    def test_to_graph_api_payload_custom_webpart(self):
        wp = WebPart(type="NewsWebPart", properties={"count": 5})
        page = SPPage(title="P", webparts=[wp])
        payload = page.to_graph_api_payload()
        webparts = payload["canvasLayout"]["horizontalSections"][0]["columns"][0]["webparts"]
        assert webparts[0]["type"] == "custom"
        assert webparts[0]["customWebPart"]["type"] == "NewsWebPart"

    def test_to_graph_api_payload_webpart_with_id(self):
        wp = WebPart(type="text", properties={"content": "Hi"}, id="abc-123")
        page = SPPage(title="P", webparts=[wp])
        payload = page.to_graph_api_payload()
        webparts = payload["canvasLayout"]["horizontalSections"][0]["columns"][0]["webparts"]
        assert webparts[0]["id"] == "abc-123"

    def test_to_graph_api_payload_webpart_without_id(self):
        wp = WebPart(type="text", properties={"content": "Hi"})
        page = SPPage(title="P", webparts=[wp])
        payload = page.to_graph_api_payload()
        webparts = payload["canvasLayout"]["horizontalSections"][0]["columns"][0]["webparts"]
        assert "id" not in webparts[0]


# ---------------------------------------------------------------------------
# CustomWebPartCode
# ---------------------------------------------------------------------------

class TestCustomWebPartCode:
    def test_valid_component(self):
        c = CustomWebPartCode(component_name="MyButton", tsx_content="const X = () => <div/>", scss_content=".x{}")
        assert c.component_name == "MyButton"

    def test_empty_component_name_raises(self):
        with pytest.raises(ValueError, match="Component name"):
            CustomWebPartCode(component_name="", tsx_content="tsx", scss_content="scss")

    def test_whitespace_component_name_raises(self):
        with pytest.raises(ValueError, match="Component name"):
            CustomWebPartCode(component_name="  ", tsx_content="tsx", scss_content="scss")

    def test_empty_tsx_raises(self):
        with pytest.raises(ValueError, match="tsx_content"):
            CustomWebPartCode(component_name="A", tsx_content="", scss_content="scss")

    def test_empty_scss_raises(self):
        with pytest.raises(ValueError, match="scss_content"):
            CustomWebPartCode(component_name="A", tsx_content="tsx", scss_content="")


# ---------------------------------------------------------------------------
# ProvisioningBlueprint
# ---------------------------------------------------------------------------

class TestProvisioningBlueprint:
    def _col(self):
        return SPColumn(name="Status", type="text", required=False)

    def _sp_list(self):
        return SPList(title="T", description="d", columns=[self._col()])

    def test_valid_blueprint_with_list(self):
        bp = ProvisioningBlueprint(reasoning="Some reason", lists=[self._sp_list()])
        assert bp.is_valid()

    def test_empty_reasoning_raises(self):
        with pytest.raises(ValueError, match="reasoning cannot be empty"):
            ProvisioningBlueprint(reasoning="", lists=[self._sp_list()])

    def test_whitespace_reasoning_raises(self):
        with pytest.raises(ValueError, match="reasoning cannot be empty"):
            ProvisioningBlueprint(reasoning="  ", lists=[self._sp_list()])

    def test_all_empty_resources_raises(self):
        with pytest.raises(ValueError, match="at least one resource"):
            ProvisioningBlueprint(reasoning="Reason")

    def test_blueprint_with_only_sites_is_valid(self):
        site = SPSite(title="S", description="d")
        bp = ProvisioningBlueprint(reasoning="R", sites=[site])
        assert bp.is_valid()

    def test_blueprint_with_only_pages_is_valid(self):
        page = SPPage(title="P", webparts=[WebPart(type="text", properties={})])
        bp = ProvisioningBlueprint(reasoning="R", pages=[page])
        assert bp.is_valid()

    def test_blueprint_with_only_libraries_is_valid(self):
        lib = DocumentLibrary(title="Docs", description="d")
        bp = ProvisioningBlueprint(reasoning="R", document_libraries=[lib])
        assert bp.is_valid()

    def test_blueprint_with_only_groups_is_valid(self):
        group = SharePointGroup(name="Owners")
        bp = ProvisioningBlueprint(reasoning="R", groups=[group])
        assert bp.is_valid()

    def test_is_valid_false_when_all_empty(self):
        # Build a valid one first then verify is_valid logic
        bp = ProvisioningBlueprint(reasoning="R", lists=[self._sp_list()])
        bp.lists = []
        bp.sites = []
        bp.pages = []
        bp.custom_components = []
        bp.document_libraries = []
        bp.groups = []
        bp.term_sets = []
        bp.content_types = []
        bp.views = []
        bp.workflows = []
        assert bp.is_valid() is False

    def test_is_valid_true_with_term_sets(self):
        from src.domain.entities.enterprise import TermSet
        bp = ProvisioningBlueprint(reasoning="R", lists=[self._sp_list()])
        bp.lists = []
        bp.term_sets = [TermSet(name="Taxonomy", terms=[], group_name="")]
        assert bp.is_valid()

    def test_get_all_accessors(self):
        sp_list = self._sp_list()
        bp = ProvisioningBlueprint(reasoning="R", lists=[sp_list])
        assert bp.get_all_lists() is bp.lists
        assert bp.get_all_sites() is bp.sites
        assert bp.get_all_pages() is bp.pages
        assert bp.get_all_document_libraries() is bp.document_libraries
        assert bp.get_all_groups() is bp.groups
