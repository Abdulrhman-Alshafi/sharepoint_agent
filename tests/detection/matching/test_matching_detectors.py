"""Unit tests for matching detectors."""

import pytest
from src.detection.matching.library_matcher import score_library_match, NOISE_WORDS
from src.detection.matching.query_classifier import classify_query_type
from src.detection.matching.location_hint_detector import detect_location_hint


class TestLibraryMatcher:
    def test_exact_match_returns_100(self):
        assert score_library_match("upload to HR Documents", "HR Documents") == 100

    def test_all_words_match_returns_50_plus(self):
        score = score_library_match("put it in human resources", "human resources")
        assert score >= 50

    def test_partial_match_returns_nonzero(self):
        score = score_library_match("HR stuff", "HR Documents")
        assert score > 0

    def test_no_match_returns_zero(self):
        assert score_library_match("create a new site", "HR Documents") == 0

    def test_noise_words_present(self):
        assert "the" in NOISE_WORDS
        assert "library" in NOISE_WORDS


class TestQueryClassifier:
    def test_count_query(self):
        r = classify_query_type("how many pages are there?")
        assert bool(r)
        assert r.intent == "count"

    def test_meta_query(self):
        r = classify_query_type("what lists are available?")
        assert bool(r)
        assert r.intent == "meta"

    def test_generic_query_returns_empty(self):
        r = classify_query_type("show me the home page content")
        assert not bool(r)


class TestLocationHintDetector:
    def test_site_keyword(self):
        r = detect_location_hint("try the HR site")
        assert bool(r)
        assert r.intent == "location_hint"

    def test_intranet_keyword(self):
        r = detect_location_hint("check the intranet")
        assert bool(r)

    def test_short_proper_noun(self):
        r = detect_location_hint("HR Portal")
        assert bool(r)

    def test_long_unrelated_message_returns_empty(self):
        r = detect_location_hint("i have no idea what you are asking me to do here")
        assert not bool(r)
