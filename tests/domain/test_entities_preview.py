"""Tests for preview/dry-run domain entities."""

import pytest
from src.domain.entities.preview import (
    OperationType,
    RiskLevel,
    WebPartType,
    ResourceChange,
    ProvisioningPreview,
    DeletionImpact,
    WebPartCatalogEntry,
    WebPartCapability,
    WebPartDecision,
    DryRunResult,
)


class TestProvisioningPreview:
    def test_add_change(self):
        preview = ProvisioningPreview(operation_type=OperationType.CREATE)
        change = ResourceChange(resource_type="list", resource_name="Tasks", change_type="add")
        preview.add_change(change)
        assert len(preview.affected_resources) == 1
        assert preview.affected_resources[0] is change

    def test_get_summary_includes_operation_type(self):
        preview = ProvisioningPreview(operation_type=OperationType.CREATE)
        summary = preview.get_summary()
        assert "CREATE" in summary

    def test_get_summary_includes_resource_names(self):
        preview = ProvisioningPreview(operation_type=OperationType.CREATE)
        preview.add_change(ResourceChange(resource_type="list", resource_name="Tasks", change_type="add"))
        summary = preview.get_summary()
        assert "Tasks" in summary

    def test_get_summary_includes_warnings(self):
        preview = ProvisioningPreview(
            operation_type=OperationType.DELETE,
            warnings=["Irreversible action", "500 items will be lost"],
        )
        summary = preview.get_summary()
        assert "Irreversible action" in summary
        assert "500 items will be lost" in summary

    def test_get_summary_includes_risk_level(self):
        preview = ProvisioningPreview(operation_type=OperationType.DELETE, risk_level=RiskLevel.HIGH)
        summary = preview.get_summary()
        assert "HIGH" in summary

    def test_get_summary_without_warnings_no_warning_section(self):
        preview = ProvisioningPreview(operation_type=OperationType.CREATE, warnings=[])
        summary = preview.get_summary()
        assert "Warnings" not in summary


class TestDeletionImpact:
    def _make_impact(self, **kwargs):
        defaults = {
            "target_resource_type": "list",
            "target_resource_id": "list-001",
            "target_resource_name": "Tasks",
        }
        defaults.update(kwargs)
        return DeletionImpact(**defaults)

    def test_get_impact_message_includes_name(self):
        impact = self._make_impact()
        msg = impact.get_impact_message()
        assert "Tasks" in msg

    def test_get_impact_message_with_dependents(self):
        impact = self._make_impact(
            dependent_resources=[
                {"name": "Calendar", "type": "list"},
                {"name": "Home", "type": "page"},
            ]
        )
        msg = impact.get_impact_message()
        assert "Calendar" in msg
        assert "Home" in msg

    def test_get_impact_message_truncates_after_5_dependents(self):
        deps = [{"name": f"Resource {i}", "type": "list"} for i in range(8)]
        impact = self._make_impact(dependent_resources=deps)
        msg = impact.get_impact_message()
        assert "3 more" in msg  # 8 - 5 = 3

    def test_get_impact_message_exactly_5_dependents_no_truncation(self):
        deps = [{"name": f"Resource {i}", "type": "list"} for i in range(5)]
        impact = self._make_impact(dependent_resources=deps)
        msg = impact.get_impact_message()
        assert "more" not in msg

    def test_get_impact_message_includes_data_loss_summary(self):
        impact = self._make_impact(data_loss_summary="500 task items will be permanently deleted")
        msg = impact.get_impact_message()
        assert "500 task items" in msg

    def test_get_impact_message_includes_item_count(self):
        impact = self._make_impact(item_count=42)
        msg = impact.get_impact_message()
        assert "42" in msg

    def test_get_impact_message_skips_item_count_when_zero(self):
        impact = self._make_impact(item_count=0)
        msg = impact.get_impact_message()
        assert "Items affected" not in msg

    def test_get_impact_message_includes_reversibility(self):
        impact = self._make_impact(reversibility="permanent")
        msg = impact.get_impact_message()
        assert "PERMANENT" in msg

    def test_get_impact_message_confirmation_text(self):
        impact = self._make_impact(confirmation_required=True)
        msg = impact.get_impact_message()
        assert "yes, delete" in msg.lower()

    def test_get_impact_message_risk_level(self):
        impact = self._make_impact(risk_level=RiskLevel.HIGH)
        msg = impact.get_impact_message()
        assert "HIGH" in msg


class TestWebPartCatalogEntry:
    def test_matches_requirement_true(self):
        entry = WebPartCatalogEntry(
            web_part_name="News",
            web_part_type="news_webpart",
            category="content",
            common_use_cases=["show company news", "display announcements"],
        )
        assert entry.matches_requirement("show company news") is True

    def test_matches_requirement_false(self):
        entry = WebPartCatalogEntry(
            web_part_name="News",
            web_part_type="news_webpart",
            category="content",
            common_use_cases=["show company news"],
        )
        assert entry.matches_requirement("manage calendar events") is False

    def test_matches_requirement_partial_match(self):
        entry = WebPartCatalogEntry(
            web_part_name="News",
            web_part_type="news_webpart",
            category="content",
            common_use_cases=["company news and updates"],
        )
        assert entry.matches_requirement("news") is True


class TestWebPartDecision:
    def test_get_explanation_builtin(self):
        catalog_entry = WebPartCatalogEntry(
            web_part_name="News",
            web_part_type="news",
            category="content",
        )
        decision = WebPartDecision(
            requirement="show news",
            recommended_type=WebPartType.BUILTIN,
            builtin_option=catalog_entry,
            reasoning="Built-in News web part covers all requirements",
        )
        explanation = decision.get_explanation()
        assert "News" in explanation
        assert "Built-in" in explanation

    def test_get_explanation_custom(self):
        decision = WebPartDecision(
            requirement="interactive dashboard",
            recommended_type=WebPartType.CUSTOM,
            custom_features_needed=["Real-time data", "Custom charts"],
            reasoning="No built-in web part supports real-time custom dashboards",
        )
        explanation = decision.get_explanation()
        assert "custom" in explanation.lower() or "SPFx" in explanation
        assert "Real-time data" in explanation


class TestDryRunResult:
    def test_get_summary_with_creates(self):
        result = DryRunResult(would_create=["Tasks list", "Home page"])
        summary = result.get_summary()
        assert "Tasks list" in summary
        assert "Home page" in summary

    def test_get_summary_with_updates(self):
        result = DryRunResult(would_update=["Announcements list"])
        summary = result.get_summary()
        assert "Announcements list" in summary

    def test_get_summary_with_deletes(self):
        result = DryRunResult(would_delete=["Old list"])
        summary = result.get_summary()
        assert "Old list" in summary

    def test_get_summary_with_errors_sets_success_false(self):
        result = DryRunResult(validation_errors=["Title is required"])
        summary = result.get_summary()
        assert "Title is required" in summary
        assert result.success is False

    def test_get_summary_ready_to_execute_when_no_errors(self):
        result = DryRunResult(would_create=["Tasks"])
        summary = result.get_summary()
        assert "Ready to execute" in summary

    def test_get_summary_includes_warnings(self):
        result = DryRunResult(validation_warnings=["Title is very long"])
        summary = result.get_summary()
        assert "Title is very long" in summary

    def test_get_summary_empty_result(self):
        result = DryRunResult()
        summary = result.get_summary()
        assert "Dry-Run" in summary
