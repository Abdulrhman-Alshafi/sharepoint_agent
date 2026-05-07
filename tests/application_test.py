"""Unit tests for application services and use cases."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.domain.entities import SPList, SPPage, ProvisioningBlueprint
from src.domain.value_objects import SPColumn, WebPart
from src.application.services import ProvisioningApplicationService
from src.application.commands import ProvisionResourcesCommand


import pytest_asyncio
import asyncio

class TestProvisioningApplicationService:
    """Test ProvisioningApplicationService."""
    
    @pytest_asyncio.fixture(autouse=True)
    async def setup_mocks(self):
        pass
        
    def test_provision_resources_success(self):
        # Setup mocks
        blueprint_generator = AsyncMock()
        sharepoint_repo = AsyncMock()
        
        # Create test blueprint
        columns = [SPColumn(name="Title", type="text", required=True)]
        sp_list = SPList(title="Test List", description="Test", columns=columns)
        blueprint = ProvisioningBlueprint(
            reasoning="Test",
            lists=[sp_list],
            pages=[]
        )
        
        blueprint_generator.generate_blueprint.return_value = blueprint
        sharepoint_repo.create_list.return_value = {"id": "list-123"}
        
        service = ProvisioningApplicationService(blueprint_generator, sharepoint_repo)
        
        
        # Execute
        result = asyncio.run(service.provision_resources("Create a list"))
        
        # Assert
        assert result.blueprint.reasoning == "Test"
        assert len(result.created_lists) == 1
        blueprint_generator.generate_blueprint.assert_called_once()
        sharepoint_repo.get_all_lists.assert_called_once()
        sharepoint_repo.create_list.assert_called_once()
