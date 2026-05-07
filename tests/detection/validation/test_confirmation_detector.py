"""Unit tests for src/detection/validation/confirmation_detector.py"""

import pytest
from src.detection.validation.confirmation_detector import detect_confirmation


class TestDetectConfirmation:
    @pytest.mark.parametrize("msg", ["yes", "yes.", "confirm", "ok", "okay", "sure", "proceed"])
    def test_exact_tokens_match(self, msg):
        r = detect_confirmation(msg)
        assert bool(r)
        assert r.intent == "confirm"

    @pytest.mark.parametrize("msg", ["yes please", "confirm it", "sure thing"])
    def test_prefix_match(self, msg):
        r = detect_confirmation(msg)
        assert bool(r)

    def test_negative_no_confirm(self):
        r = detect_confirmation("no I don't want that")
        assert not bool(r)

    def test_empty_string(self):
        r = detect_confirmation("")
        assert not bool(r)
