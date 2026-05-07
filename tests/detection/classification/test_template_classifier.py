"""Unit tests for src/detection/classification/template_classifier.py"""

import pytest
from unittest.mock import MagicMock
from src.detection.classification.template_classifier import classify_template


def _make_template(name: str, keywords: tuple):
    t = MagicMock()
    t.name = name
    t.keywords = keywords
    return t


class TestClassifyTemplate:
    def test_returns_matching_template(self):
        templates = [
            _make_template("HR Intranet", ("hr", "human resources", "employees")),
            _make_template("Project Site", ("project", "tasks", "milestones")),
        ]
        result = classify_template("create an HR intranet for us", templates)
        assert result is not None
        assert result.name == "HR Intranet"

    def test_returns_none_when_no_match(self):
        templates = [
            _make_template("Sales Portal", ("sales", "revenue", "crm")),
        ]
        result = classify_template("set up a finance workspace", templates)
        assert result is None

    def test_empty_template_list(self):
        result = classify_template("any message", [])
        assert result is None

    def test_highest_score_wins(self):
        templates = [
            _make_template("TeamA", ("project", "tasks")),
            _make_template("TeamB", ("project", "tasks", "milestones", "roadmap")),
        ]
        result = classify_template("project with tasks milestones and roadmap", templates)
        assert result is not None
        assert result.name == "TeamB"
