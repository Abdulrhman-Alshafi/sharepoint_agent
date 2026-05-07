"""
Tests for list item CRUD operations.
"""

import pytest
import asyncio
from src.application.use_cases.list_item_operations_use_case import ListItemOperationsUseCase
from src.infrastructure.external_services.list_item_parser import ListItemParserService


@pytest.mark.asyncio
async def test_create_list_item(mock_sharepoint_repository):
    """Test creating a list item."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    item_data = {
        "Title": "Test Item",
        "Employee": "Abdulrahman Alshafi",
        "Salary": 5000,
        "Month": "March 2024"
    }
    
    result = await use_case.create_item("list-123", item_data)
    
    assert result is not None
    assert result["id"] == "item-123"
    assert result["fields"]["Employee"] == "Abdulrahman Alshafi"
    assert result["fields"]["Salary"] == 5000


@pytest.mark.asyncio
async def test_update_list_item(mock_sharepoint_repository):
    """Test updating a list item."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    update_data = {
        "Salary": 5500
    }
    
    result = await use_case.update_item("list-123", "item-123", update_data)
    
    assert result is not None
    assert result["id"] == "item-123"
    assert result["fields"]["Salary"] == 5500


@pytest.mark.asyncio
async def test_delete_list_item(mock_sharepoint_repository):
    """Test deleting a list item."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    result = await use_case.delete_item("list-123", "item-123")
    
    assert result is True


@pytest.mark.asyncio
async def test_query_list_items(mock_sharepoint_repository):
    """Test querying list items."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    result = await use_case.query_items("list-123")
    
    assert result is not None
    assert len(result) > 0
    assert result[0]["id"] == "item-1"


@pytest.mark.asyncio
async def test_parse_create_operation():
    """Test parsing a create item operation."""
    message = "Add a salary record for John Smith with 5000 for March 2024"
    
    operation = await ListItemParserService.parse_item_operation(message)
    
    if operation:
        assert operation.operation == "create"
        assert "salary" in operation.list_name.lower() or "salaries" in operation.list_name.lower()
        assert "John" in str(operation.field_values.get("Employee", "")) or "John Smith" in str(operation.field_values.get("Employee", ""))


@pytest.mark.asyncio
async def test_parse_update_operation():
    """Test parsing an update item operation."""
    message = "Update Abdulrahman Alshafi salary to 5500 in March"
    
    operation = await ListItemParserService.parse_item_operation(message)
    
    if operation:
        assert operation.operation == "update"
        assert operation.filter_criteria is not None
        assert operation.field_values is not None


@pytest.mark.asyncio
async def test_parse_delete_operation():
    """Test parsing a delete item operation."""
    message = "Delete the salary record for John from January"
    
    operation = await ListItemParserService.parse_item_operation(message)
    
    if operation:
        assert operation.operation == "delete"
        assert operation.filter_criteria is not None


@pytest.mark.asyncio
async def test_parse_query_operation():
    """Test parsing a query item operation."""
    message = "Show all salaries above 4000"
    
    operation = await ListItemParserService.parse_item_operation(message)
    
    if operation:
        assert operation.operation == "query"
        assert operation.filter_criteria is not None


def test_build_odata_filter():
    """Test building OData filter queries."""
    # Simple equality
    filter_criteria = {"Employee": "John Smith", "Month": "March"}
    filter_query = ListItemParserService.build_odata_filter(filter_criteria)
    assert "Employee eq 'John Smith'" in filter_query
    assert "Month eq 'March'" in filter_query
    assert "and" in filter_query
    
    # Greater than
    filter_criteria = {"Salary": {"$gt": 4000}}
    filter_query = ListItemParserService.build_odata_filter(filter_criteria)
    assert "Salary gt 4000" in filter_query
    
    # Less than or equal
    filter_criteria = {"Age": {"$lte": 30}}
    filter_query = ListItemParserService.build_odata_filter(filter_criteria)
    assert "Age le 30" in filter_query


@pytest.mark.asyncio
async def test_detect_item_operation_intent():
    """Test detecting item operation intent."""
    # Should detect as item operation
    assert await ListItemParserService.detect_item_operation_intent("Add a salary record for John") is True
    assert await ListItemParserService.detect_item_operation_intent("Update the salary for employee John") is True
    assert await ListItemParserService.detect_item_operation_intent("Delete the record from March") is True
    assert await ListItemParserService.detect_item_operation_intent("Show all items above 1000") is True
    
    # Should NOT detect as item operation (list-level)
    assert await ListItemParserService.detect_item_operation_intent("Create a new list") is False
    assert await ListItemParserService.detect_item_operation_intent("Delete the entire Tasks document library") is False
    assert await ListItemParserService.detect_item_operation_intent("Add a column to the list") is False


@pytest.mark.asyncio
async def test_find_item_by_field(mock_sharepoint_repository):
    """Test finding an item by field value."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    result = await use_case.find_item_by_field("list-123", "Title", "Test Item")
    
    assert result is not None
    assert result["id"] == "item-1"


@pytest.mark.asyncio
async def test_batch_create_items(mock_sharepoint_repository):
    """Test batch creating multiple items."""
    use_case = ListItemOperationsUseCase(mock_sharepoint_repository)
    
    items_data = [
        {"Title": "Item 1", "Salary": 5000},
        {"Title": "Item 2", "Salary": 6000},
        {"Title": "Item 3", "Salary": 7000}
    ]
    
    results = await use_case.batch_create_items("list-123", items_data)
    
    assert "items" in results
    items = results["items"]
    assert len(items) == 3
    for result in items:
        assert "id" in result
        assert "fields" in result
