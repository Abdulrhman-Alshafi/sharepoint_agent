"""Tests for ConversationStateRepository."""

import time
import pytest
from unittest.mock import patch

from src.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from src.domain.entities.conversation import ConversationState, ConversationContext


def _make_state(session_id: str = "sess-001") -> ConversationState:
    from src.domain.entities.conversation import GatheringPhase
    return ConversationState(session_id=session_id, phase=GatheringPhase.INTENT_DETECTED)


class TestSaveAndGet:
    def test_save_then_get_returns_state(self):
        repo = ConversationStateRepository()
        state = _make_state("s1")
        repo.save(state)
        result = repo.get("s1")
        assert result is state

    def test_get_nonexistent_returns_none(self):
        repo = ConversationStateRepository()
        assert repo.get("does-not-exist") is None

    def test_save_updates_existing(self):
        repo = ConversationStateRepository()
        s = _make_state("s1")
        repo.save(s)
        repo.save(s)
        assert repo.get("s1") is s

    def test_save_multiple_sessions(self):
        repo = ConversationStateRepository()
        for i in range(5):
            repo.save(_make_state(f"session-{i}"))
        assert repo.get_active_count() == 5


class TestExpiry:
    def test_expired_state_not_returned(self):
        repo = ConversationStateRepository(ttl_seconds=1)
        state = _make_state("s2")
        repo.save(state)
        # Freeze time: patch is_expired to return True
        with patch.object(state, "is_expired", return_value=True):
            assert repo.get("s2") is None

    def test_non_expired_state_returned(self):
        repo = ConversationStateRepository(ttl_seconds=3600)
        state = _make_state("s3")
        repo.save(state)
        with patch.object(state, "is_expired", return_value=False):
            assert repo.get("s3") is state


class TestDelete:
    def test_delete_existing_returns_true(self):
        repo = ConversationStateRepository()
        repo.save(_make_state("s4"))
        assert repo.delete("s4") is True

    def test_delete_existing_removes_state(self):
        repo = ConversationStateRepository()
        repo.save(_make_state("s5"))
        repo.delete("s5")
        assert repo.get("s5") is None

    def test_delete_nonexistent_returns_false(self):
        repo = ConversationStateRepository()
        assert repo.delete("ghost") is False


class TestClearAll:
    def test_clear_all_removes_all_states(self):
        repo = ConversationStateRepository()
        for i in range(3):
            repo.save(_make_state(f"s{i}"))
        repo.clear_all()
        assert repo.get_active_count() == 0

    def test_clear_all_then_save_works(self):
        repo = ConversationStateRepository()
        repo.save(_make_state("s1"))
        repo.clear_all()
        repo.save(_make_state("s2"))
        assert repo.get("s2") is not None
        assert repo.get("s1") is None


class TestGetActiveCount:
    def test_empty_repo_count_is_zero(self):
        repo = ConversationStateRepository()
        assert repo.get_active_count() == 0

    def test_count_matches_saved(self):
        repo = ConversationStateRepository()
        repo.save(_make_state("a"))
        repo.save(_make_state("b"))
        assert repo.get_active_count() == 2

    def test_expired_not_counted(self):
        repo = ConversationStateRepository(ttl_seconds=1)
        state_a = _make_state("a")
        state_b = _make_state("b")
        repo.save(state_a)
        repo.save(state_b)
        with patch.object(state_a, "is_expired", return_value=True), \
             patch.object(state_b, "is_expired", return_value=False):
            count = repo.get_active_count()
        assert count == 1


class TestContextManagement:
    def test_save_and_load_context(self):
        repo = ConversationStateRepository()
        ctx = ConversationContext()
        repo.save_conversation_context("s1", ctx)
        loaded = repo.load_conversation_context("s1")
        assert loaded is ctx

    def test_load_nonexistent_context_returns_none(self):
        repo = ConversationStateRepository()
        assert repo.load_conversation_context("missing") is None

    def test_get_or_create_creates_when_missing(self):
        repo = ConversationStateRepository()
        ctx = repo.get_or_create_context("new-session")
        assert isinstance(ctx, ConversationContext)

    def test_get_or_create_returns_existing(self):
        repo = ConversationStateRepository()
        ctx = ConversationContext()
        repo.save_conversation_context("s2", ctx)
        same = repo.get_or_create_context("s2")
        assert same is ctx
