"""Unit tests for src/detection/base.py"""

import pytest
from src.detection.base import (
    DetectionResult,
    WEIGHT_EXPLICIT,
    WEIGHT_KEYWORD,
    WEIGHT_CONTEXTUAL,
    score_phrases,
    score_any_token,
    log_detection,
)


class TestDetectionResult:
    def test_bool_true_when_intent_set(self):
        r = DetectionResult(intent="test", score=0.9, layer="l1")
        assert bool(r) is True

    def test_bool_false_when_no_intent(self):
        assert bool(DetectionResult()) is False

    def test_is_detected_default_threshold(self):
        r = DetectionResult(intent="test", score=0.1, layer="l1")
        assert r.is_detected() is True

    def test_is_detected_false_below_threshold(self):
        r = DetectionResult(intent="test", score=0.0, layer="l1")
        assert r.is_detected() is False

    def test_is_detected_custom_threshold(self):
        r = DetectionResult(intent="test", score=0.4, layer="l1")
        assert r.is_detected(threshold=0.5) is False

    def test_empty_result_has_no_intent(self):
        r = DetectionResult()
        assert r.intent is None
        assert r.score == 0.0


class TestWeightConstants:
    def test_weight_ordering(self):
        assert WEIGHT_EXPLICIT > WEIGHT_KEYWORD > WEIGHT_CONTEXTUAL
        assert WEIGHT_EXPLICIT == 0.9
        assert WEIGHT_KEYWORD == 0.6
        assert WEIGHT_CONTEXTUAL == 0.3


class TestScorePhrases:
    def test_returns_weight_on_match(self):
        score, matched = score_phrases("create a page", ("create a page", "new page"), WEIGHT_EXPLICIT)
        assert score == WEIGHT_EXPLICIT
        assert "create a page" in matched

    def test_returns_zero_on_no_match(self):
        score, matched = score_phrases("hello world", ("create a page",), WEIGHT_EXPLICIT)
        assert score == 0.0
        assert matched == []

    def test_case_insensitive_caller_responsibility(self):
        # score_phrases does substring matching; caller must lower-case first
        score, _ = score_phrases("Create A Page", ("create a page",), WEIGHT_KEYWORD)
        # The phrase "create a page" is NOT in "Create A Page" due to case
        assert score == 0.0

    def test_lowercased_input_matches(self):
        score, _ = score_phrases("create a page", ("create a page",), WEIGHT_KEYWORD)
        assert score == WEIGHT_KEYWORD


class TestScoreAnyToken:
    def test_intersection_returns_weight(self):
        score, matched = score_any_token(
            frozenset({"page", "create"}),
            frozenset({"page", "site"}),
            WEIGHT_KEYWORD,
        )
        assert score == WEIGHT_KEYWORD
        assert "page" in matched

    def test_no_intersection_returns_zero(self):
        score, matched = score_any_token(
            frozenset({"hello"}),
            frozenset({"world"}),
            WEIGHT_KEYWORD,
        )
        assert score == 0.0
        assert matched == []


class TestLogDetection:
    def test_does_not_raise(self):
        import logging
        logger = logging.getLogger("test")
        log_detection(logger, "test.domain", {"intent_a": 0.9}, "intent_a")
