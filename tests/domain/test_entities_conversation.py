"""Tests for conversation and requirement gathering domain entities."""

import time
import pytest
from src.domain.entities.conversation import (
    GatheringPhase,
    ResourceType,
    ResourceSpecification,
    ConversationState,
    ConversationContext,
    FieldSource,
)


class TestGatheringPhase:
    def test_all_values(self):
        expected = {"INTENT_DETECTED", "GATHERING_DETAILS", "CONFIRMATION", "RISK_CONFIRMATION", "COMPLETE"}
        assert {p.value for p in GatheringPhase} == expected


class TestResourceType:
    def test_all_values(self):
        expected = {"SITE", "LIST", "PAGE", "LIBRARY", "GROUP", "CONTENT_TYPE", "TERM_SET", "VIEW"}
        assert {r.value for r in ResourceType} == expected


class TestResourceSpecification:
    def test_complete_when_all_required_fields_present(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={"title": "Tasks", "description": "d"},
            required_fields=["title", "description"],
        )
        assert spec.is_complete() is True

    def test_incomplete_when_field_missing(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={"title": "Tasks"},
            required_fields=["title", "description"],
        )
        assert spec.is_complete() is False

    def test_incomplete_when_field_is_none(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={"title": None},
            required_fields=["title"],
        )
        assert spec.is_complete() is False

    def test_complete_when_no_required_fields(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={},
            required_fields=[],
        )
        assert spec.is_complete() is True

    def test_completion_percentage_zero(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={},
            required_fields=["title", "description", "owner"],
        )
        assert spec.get_completion_percentage() == 0

    def test_completion_percentage_partial(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={"title": "Tasks"},
            required_fields=["title", "description"],
        )
        assert spec.get_completion_percentage() == 50

    def test_completion_percentage_full(self):
        spec = ResourceSpecification(
            resource_type=ResourceType.LIST,
            collected_fields={"title": "T", "description": "d"},
            required_fields=["title", "description"],
        )
        assert spec.get_completion_percentage() == 100

    def test_completion_percentage_100_when_no_required(self):
        spec = ResourceSpecification(resource_type=ResourceType.LIST)
        assert spec.get_completion_percentage() == 100


class TestConversationState:
    def _make_state(self):
        return ConversationState(
            session_id="sess-001",
            phase=GatheringPhase.GATHERING_DETAILS,
        )

    def test_get_current_spec_valid_index(self):
        spec = ResourceSpecification(resource_type=ResourceType.LIST)
        state = self._make_state()
        state.resource_specs = [spec]
        state.current_resource_index = 0
        assert state.get_current_spec() is spec

    def test_get_current_spec_out_of_range_returns_none(self):
        state = self._make_state()
        state.resource_specs = []
        state.current_resource_index = 0
        assert state.get_current_spec() is None

    def test_get_current_spec_negative_index_returns_none(self):
        state = self._make_state()
        state.resource_specs = [ResourceSpecification(resource_type=ResourceType.LIST)]
        state.current_resource_index = -1
        assert state.get_current_spec() is None

    def test_mark_updated_advances_timestamp(self):
        state = self._make_state()
        old = state.updated_at
        time.sleep(0.01)
        state.mark_updated()
        assert state.updated_at > old

    def test_is_expired_false_for_fresh_state(self):
        state = self._make_state()
        assert state.is_expired() is False

    def test_is_expired_true_when_old(self):
        state = self._make_state()
        # Fake an old timestamp
        state.updated_at = time.time() - 3700  # older than default 1800s
        assert state.is_expired() is True

    def test_is_expired_respects_custom_ttl(self):
        state = self._make_state()
        state.updated_at = time.time() - 10
        assert state.is_expired(ttl_seconds=5) is True
        assert state.is_expired(ttl_seconds=60) is False


class TestConversationContext:
    def test_add_fact_stores_value(self):
        ctx = ConversationContext()
        ctx.add_fact("title", "My List", confidence=0.9)
        assert ctx.get_fact("title") == "My List"

    def test_add_fact_clamps_confidence_above_1(self):
        ctx = ConversationContext()
        ctx.add_fact("x", "v", confidence=1.5)
        assert ctx.confidence_scores["x"] == 1.0

    def test_add_fact_clamps_confidence_below_0(self):
        ctx = ConversationContext()
        ctx.add_fact("x", "v", confidence=-0.5)
        assert ctx.confidence_scores["x"] == 0.0

    def test_get_fact_returns_none_when_missing(self):
        ctx = ConversationContext()
        assert ctx.get_fact("nonexistent") is None

    def test_has_confidence_true_above_threshold(self):
        ctx = ConversationContext()
        ctx.add_fact("title", "T", confidence=0.95)
        assert ctx.has_confidence("title", min_confidence=0.8) is True

    def test_has_confidence_false_below_threshold(self):
        ctx = ConversationContext()
        ctx.add_fact("title", "T", confidence=0.6)
        assert ctx.has_confidence("title", min_confidence=0.8) is False

    def test_has_confidence_false_when_fact_missing(self):
        ctx = ConversationContext()
        assert ctx.has_confidence("nonexistent") is False

    def test_merge_facts_user_stated_sets_confidence_1(self):
        ctx = ConversationContext()
        ctx.merge_facts({"title": "Tasks"}, source="user_stated")
        assert ctx.confidence_scores["title"] == 1.0

    def test_merge_facts_other_source_sets_confidence_07(self):
        ctx = ConversationContext()
        ctx.merge_facts({"title": "Tasks"}, source="inferred")
        assert ctx.confidence_scores["title"] == 0.7

    def test_merge_facts_merges_all_keys(self):
        ctx = ConversationContext()
        ctx.merge_facts({"a": 1, "b": 2})
        assert ctx.get_fact("a") == 1
        assert ctx.get_fact("b") == 2

    def test_add_recent_resource_inserts_at_front(self):
        ctx = ConversationContext()
        ctx.add_recent_resource("list", "id-1", "Tasks")
        ctx.add_recent_resource("page", "id-2", "Home")
        assert ctx.recent_resources[0]["type"] == "page"

    def test_add_recent_resource_caps_at_50(self):
        ctx = ConversationContext()
        for i in range(55):
            ctx.add_recent_resource("list", f"id-{i}", f"List {i}")
        assert len(ctx.recent_resources) == 50

    def test_add_recent_resource_stores_metadata(self):
        ctx = ConversationContext()
        ctx.add_recent_resource("list", "id-1", "Tasks", metadata={"color": "blue"})
        assert ctx.recent_resources[0]["metadata"]["color"] == "blue"


class TestFieldSource:
    def test_get_indicator_user_stated(self):
        fs = FieldSource(field_name="title", value="Tasks", source="user_stated", confidence=1.0)
        assert fs.get_indicator() == "✓"

    def test_get_indicator_context(self):
        fs = FieldSource(field_name="title", value="Tasks", source="context", confidence=0.9)
        assert fs.get_indicator() == "↻"

    def test_get_indicator_inferred(self):
        fs = FieldSource(field_name="title", value="Tasks", source="inferred", confidence=0.7)
        assert fs.get_indicator() == "~"

    def test_get_indicator_default(self):
        fs = FieldSource(field_name="title", value="Tasks", source="default", confidence=0.5)
        assert fs.get_indicator() == "*"
