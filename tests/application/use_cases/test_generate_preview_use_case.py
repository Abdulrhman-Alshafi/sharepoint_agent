"""Tests for GeneratePreviewUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.use_cases.generate_preview_use_case import GeneratePreviewUseCase
from src.domain.entities.preview import ProvisioningPreview, OperationType, RiskLevel


def _make_blueprint(lists=None, pages=None):
    from src.domain.entities.core import ProvisioningBlueprint, SPSite, SPList, ActionType
    from src.domain.value_objects import SPColumn
    return ProvisioningBlueprint(
        reasoning="test",
        lists=lists or [],
        pages=pages or [],
        custom_components=[],
        document_libraries=[],
        groups=[],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[],
        content_types=[],
        views=[],
        workflows=[],
    )


class TestGeneratePreviewUseCaseExecute:
    @pytest.mark.asyncio
    async def test_returns_provisioning_preview(self):
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        bp = _make_blueprint()

        with patch.object(uc, "_analyze_list_change", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_analyze_page_change", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_analyze_library_change", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_analyze_group_change", new=AsyncMock(return_value=MagicMock())):
            result = await uc.execute(bp, "site-1")

        assert isinstance(result, ProvisioningPreview)

    @pytest.mark.asyncio
    async def test_analyzes_all_lists(self):
        from src.domain.entities.core import SPList, ActionType
        from src.domain.value_objects import SPColumn
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        col = SPColumn(name="Status", type="text", required=False)
        lists = [
            SPList(title="A", description="", columns=[col], action=ActionType.CREATE),
            SPList(title="B", description="", columns=[col], action=ActionType.CREATE),
        ]
        bp = _make_blueprint(lists=lists)

        mock_change = MagicMock()
        with patch.object(uc, "_analyze_list_change", new=AsyncMock(return_value=mock_change)) as mock_analyze, \
             patch.object(uc, "_analyze_page_change", new=AsyncMock(return_value=mock_change)), \
             patch.object(uc, "_analyze_library_change", new=AsyncMock(return_value=mock_change)), \
             patch.object(uc, "_analyze_group_change", new=AsyncMock(return_value=mock_change)):
            await uc.execute(bp, "site-1")

        assert mock_analyze.await_count == 2

    def test_determine_operation_type_create(self):
        from src.domain.entities.core import SPList, ActionType
        from src.domain.value_objects import SPColumn
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        col = SPColumn(name="S", type="text", required=False)
        bp = _make_blueprint(lists=[SPList(title="T", description="", columns=[col], action=ActionType.CREATE)])
        result = uc._determine_operation_type(bp)
        assert result == OperationType.CREATE

    def test_determine_operation_type_delete(self):
        from src.domain.entities.core import SPList, ActionType
        from src.domain.value_objects import SPColumn
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        col = SPColumn(name="S", type="text", required=False)
        bp = _make_blueprint(lists=[SPList(title="T", description="", columns=[col], action=ActionType.DELETE, list_id="id")])
        result = uc._determine_operation_type(bp)
        assert result == OperationType.DELETE

    def test_determine_operation_type_empty_blueprint(self):
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        bp = _make_blueprint()
        result = uc._determine_operation_type(bp)
        assert result == OperationType.CREATE

    def test_assess_risk_level_low_for_creates(self):
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        mock_change = MagicMock()
        mock_change.operation_type = OperationType.CREATE
        risk = uc._assess_risk_level([mock_change])
        assert risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)

    def test_estimate_duration_returns_positive_int(self):
        repo = AsyncMock()
        uc = GeneratePreviewUseCase(repo)
        duration = uc._estimate_duration([MagicMock(), MagicMock()])
        assert duration > 0
