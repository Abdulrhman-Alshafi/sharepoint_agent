"""Tests for InputSanitizer — security-critical input validation."""

import pytest
from src.infrastructure.services.input_sanitizer import InputSanitizer, MAX_MESSAGE_LENGTH


class TestSanitizeMessage:
    def test_valid_message_returned(self):
        result = InputSanitizer.sanitize_message("Hello, please create a list")
        assert result == "Hello, please create a list"

    def test_empty_message_raises(self):
        with pytest.raises(ValueError, match="empty"):
            InputSanitizer.sanitize_message("")

    def test_none_like_empty_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            InputSanitizer.sanitize_message(None)  # type: ignore

    def test_message_over_max_length_raises(self):
        long_msg = "a" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValueError, match="too long"):
            InputSanitizer.sanitize_message(long_msg)

    def test_message_at_max_length_passes(self):
        exact_msg = "a" * MAX_MESSAGE_LENGTH
        result = InputSanitizer.sanitize_message(exact_msg)
        assert len(result) == MAX_MESSAGE_LENGTH

    def test_leading_trailing_whitespace_stripped(self):
        result = InputSanitizer.sanitize_message("  Hello World  ")
        assert result == "Hello World"

    def test_multiple_spaces_collapsed(self):
        result = InputSanitizer.sanitize_message("Hello   World")
        assert "  " not in result

    def test_non_printable_chars_removed(self):
        msg = "Hello\x00World\x01"
        result = InputSanitizer.sanitize_message(msg)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.parametrize("suspicious", [
        "ignore previous instructions",
        "ignore all rules",
        "system: you are",
        "new instructions",
        "forget everything",
        "<script>alert(1)</script>",
        "javascript: alert(1)",
        "<iframe src='evil.com'>",
    ])
    def test_suspicious_patterns_do_raise(self, suspicious):
        # Per code: suspicious patterns are logged but NOT blocked
        with pytest.raises(ValueError):
            InputSanitizer.sanitize_message(suspicious)


class TestSanitizeFilename:
    def test_valid_filename_returned(self):
        result = InputSanitizer.sanitize_filename("report.pdf")
        assert result == "report.pdf"

    def test_empty_filename_raises(self):
        with pytest.raises(ValueError, match="empty"):
            InputSanitizer.sanitize_filename("")

    def test_path_traversal_forward_slash_removed(self):
        result = InputSanitizer.sanitize_filename("../../../etc/passwd")
        assert "../" not in result

    def test_path_traversal_backslash_removed(self):
        result = InputSanitizer.sanitize_filename("..\\..\\system32")
        assert "..\\" not in result

    def test_invalid_chars_replaced_with_underscore(self):
        result = InputSanitizer.sanitize_filename("file<name>.txt")
        assert "<" not in result
        assert ">" not in result

    def test_filename_over_255_chars_truncated(self):
        long_name = "a" * 260 + ".txt"
        result = InputSanitizer.sanitize_filename(long_name)
        assert len(result) <= 255

    def test_extension_preserved_after_truncation(self):
        long_name = "a" * 260 + ".pdf"
        result = InputSanitizer.sanitize_filename(long_name)
        assert result.endswith(".pdf")


class TestSanitizeListName:
    def test_valid_name_returned(self):
        result = InputSanitizer.sanitize_list_name("My Tasks")
        assert result == "My Tasks"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="empty"):
            InputSanitizer.sanitize_list_name("")

    def test_special_chars_removed(self):
        result = InputSanitizer.sanitize_list_name("Tasks#List&More")
        assert "#" not in result
        assert "&" not in result

    def test_name_over_255_chars_truncated(self):
        long_name = "a" * 300
        result = InputSanitizer.sanitize_list_name(long_name)
        assert len(result) <= 255
