"""Unit tests for src/detection/classification/page_purpose_classifier.py"""

import pytest
from src.detection.classification.page_purpose_classifier import classify_page_purpose


class TestClassifyPagePurpose:
    def test_home_page(self):
        purpose, confidence = classify_page_purpose("Welcome to our Home Page")
        assert purpose == "Home"
        assert confidence > 0.0

    def test_news_page(self):
        purpose, confidence = classify_page_purpose("Company News and Announcements")
        assert purpose == "News"

    def test_faq_page(self):
        purpose, confidence = classify_page_purpose("Frequently Asked Questions")
        assert purpose == "FAQ"
        assert confidence > 0.0

    def test_no_match_returns_other(self):
        purpose, confidence = classify_page_purpose("xyz abc 123")
        assert purpose == "Other"

    def test_description_contributes(self):
        purpose, confidence = classify_page_purpose("Internal", "HR onboarding guide for new hire orientation")
        assert purpose in ("Documentation", "ResourceLibrary", "Team")  # any plausible match
