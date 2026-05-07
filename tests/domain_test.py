"""Unit tests for domain entities."""

import pytest
from src.domain.entities import SPList, SPPage, ProvisioningBlueprint, ActionType, DataQueryResult
from src.domain.value_objects import SPColumn, WebPart
from src.domain.exceptions import InvalidBlueprintException


class TestDataQueryResult:
    """Test DataQueryResult entity."""
    
    def test_create_valid_query_result(self):
        result = DataQueryResult(
            answer="There are 5 tasks.",
            data_summary={"count": 5},
            source_list="Tasks",
            resource_link="http://link",
            suggested_actions=["Create summary"]
        )
        assert result.answer == "There are 5 tasks."
        assert "count" in result.data_summary
        assert result.source_list == "Tasks"
        assert result.resource_link == "http://link"
        assert len(result.suggested_actions) == 1


class TestSPColumn:
    """Test SPColumn value object."""
    
    def test_create_valid_column(self):
        col = SPColumn(name="Title", type="text", required=True)
        assert col.name == "Title"
        assert col.type == "text"
        assert col.required is True
    
    def test_create_column_empty_name_raises_error(self):
        with pytest.raises(ValueError):
            SPColumn(name="", type="text", required=False)


class TestSPList:
    """Test SPList entity."""
    
    def test_create_valid_list(self):
        columns = [SPColumn(name="ID", type="text", required=True)]
        sp_list = SPList(title="My List", description="Test list", columns=columns, action=ActionType.UPDATE)
        assert sp_list.title == "My List"
        assert len(sp_list.columns) == 1
        assert sp_list.action == ActionType.UPDATE
    
    def test_create_list_empty_title_raises_error(self):
        with pytest.raises(ValueError):
            SPList(title="", description="Test", columns=[])


class TestProvisioningBlueprint:
    """Test ProvisioningBlueprint entity."""
    
    def test_create_valid_blueprint(self):
        columns = [SPColumn(name="Title", type="text", required=True)]
        sp_list = SPList(title="List1", description="Test", columns=columns)
        blueprint = ProvisioningBlueprint(
            reasoning="Need a list",
            lists=[sp_list],
            pages=[]
        )
        assert blueprint.is_valid()
    
    def test_create_valid_custom_component_blueprint(self):
        from src.domain.entities import CustomWebPartCode

        custom_component = CustomWebPartCode(
            component_name="CustomSwiper",
            tsx_content="export const CustomSwiper = () => <div>Swiper</div>;",
            scss_content=".customSwiper { display: block; }"
        )

        blueprint = ProvisioningBlueprint(
            reasoning="Need a custom web part",
            lists=[],
            pages=[],
            custom_components=[custom_component]
        )

        assert blueprint.is_valid()
        assert blueprint.get_all_custom_components()[0].component_name == "CustomSwiper"

    def test_is_valid_empty_blueprint_raises_error(self):
        with pytest.raises(ValueError):
            ProvisioningBlueprint(reasoning="Test", lists=[], pages=[])
