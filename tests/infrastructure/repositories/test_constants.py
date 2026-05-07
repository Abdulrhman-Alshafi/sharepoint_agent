"""Tests for SharePointConstants."""

import pytest

from src.infrastructure.repositories.utils.constants import SharePointConstants


class TestSharePointConstants:
    def test_max_batch_size(self):
        assert SharePointConstants.MAX_BATCH_SIZE == 20

    def test_max_pages_to_fetch(self):
        assert SharePointConstants.MAX_PAGES_TO_FETCH == 20

    def test_items_per_page(self):
        assert SharePointConstants.ITEMS_PER_PAGE == 500

    def test_text_webpart_control_type(self):
        assert SharePointConstants.TEXT_WEBPART_CONTROL_TYPE == 4

    def test_client_webpart_control_type(self):
        assert SharePointConstants.CLIENT_WEBPART_CONTROL_TYPE == 3

    def test_conversation_state_ttl(self):
        assert SharePointConstants.CONVERSATION_STATE_TTL_MINUTES == 30

    def test_protected_columns_contains_title(self):
        # The actual set uses lowercase values like "title", "id" etc.
        pc = {v.lower() for v in SharePointConstants.PROTECTED_COLUMNS}
        assert "title" in pc

    def test_protected_columns_contains_id(self):
        pc = {v.lower() for v in SharePointConstants.PROTECTED_COLUMNS}
        assert "id" in pc

    def test_protected_columns_is_iterable(self):
        # Should be a list/set/tuple of strings
        assert len(list(SharePointConstants.PROTECTED_COLUMNS)) > 0
