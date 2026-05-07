"""Tests for CanvasContentBuilder."""

import json
import pytest
from src.infrastructure.repositories.utils.canvas_builder import CanvasContentBuilder
from src.domain.value_objects import WebPart


class TestCanvasContentBuilder:
    def test_empty_list_returns_empty_json_array(self):
        result = CanvasContentBuilder.build([])
        assert result == "[]"

    def test_text_webpart_has_control_type_4(self):
        wp = WebPart(type="text", properties={"content": "Hello World"})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert len(canvas) == 1
        assert canvas[0]["controlType"] == 4

    def test_rte_webpart_has_control_type_4(self):
        wp = WebPart(type="rte", properties={"content": "Rich text"})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert canvas[0]["controlType"] == 4

    def test_custom_webpart_has_control_type_3(self):
        wp = WebPart(type="NewsWebPart", properties={"count": 5})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert canvas[0]["controlType"] == 3

    def test_text_webpart_innerHTML_from_content(self):
        wp = WebPart(type="text", properties={"content": "Hello World"})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert canvas[0]["innerHTML"] == "Hello World"

    def test_text_webpart_innerHTML_from_text_fallback(self):
        wp = WebPart(type="text", properties={"text": "Fallback text"})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert canvas[0]["innerHTML"] == "Fallback text"

    def test_custom_webpart_has_web_part_data(self):
        wp = WebPart(type="NewsWebPart", properties={"count": 5})
        result = CanvasContentBuilder.build([wp])
        canvas = json.loads(result)
        assert "webPartData" in canvas[0]
        assert canvas[0]["webPartData"]["title"] == "NewsWebPart"
        assert canvas[0]["webPartData"]["properties"] == {"count": 5}

    def test_multiple_webparts_ordering(self):
        wps = [
            WebPart(type="text", properties={"content": "First"}),
            WebPart(type="text", properties={"content": "Second"}),
        ]
        result = CanvasContentBuilder.build(wps)
        canvas = json.loads(result)
        assert len(canvas) == 2
        assert canvas[0]["innerHTML"] == "First"
        assert canvas[1]["innerHTML"] == "Second"

    def test_position_has_correct_control_index(self):
        wps = [
            WebPart(type="text", properties={"content": "A"}),
            WebPart(type="text", properties={"content": "B"}),
        ]
        result = CanvasContentBuilder.build(wps)
        canvas = json.loads(result)
        assert canvas[0]["position"]["controlIndex"] == 1
        assert canvas[1]["position"]["controlIndex"] == 2

    def test_result_is_valid_json(self):
        wp = WebPart(type="text", properties={"content": "test"})
        result = CanvasContentBuilder.build([wp])
        parsed = json.loads(result)
        assert isinstance(parsed, list)
