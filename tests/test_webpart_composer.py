"""Tests for WebPartComposer utility."""

import pytest
from src.domain.value_objects import WebPart
from src.infrastructure.repositories.utils.webpart_composer import WebPartComposer


class TestWebPartComposer:
    """Test suite for WebPartComposer."""

    def test_replace_placeholders_simple(self):
        """Test simple placeholder replacement."""
        text = "Welcome {PAGE_TITLE}"
        content = {"hero_title": "To Our Site"}
        
        result = WebPartComposer._replace_placeholders(text, content)
        assert result == "Welcome To Our Site"

    def test_replace_multiple_placeholders(self):
        """Test replacing multiple placeholders."""
        text = "{PAGE_TITLE} - {PAGE_DESCRIPTION}"
        content = {
            "hero_title": "Welcome",
            "hero_description": "To our organization"
        }
        
        result = WebPartComposer._replace_placeholders(text, content)
        assert result == "Welcome - To our organization"

    def test_replace_missing_placeholder(self):
        """Test handling of missing placeholder values."""
        text = "Title: {PAGE_TITLE}"
        content = {}  # No hero_title provided
        
        result = WebPartComposer._replace_placeholders(text, content)
        assert result == "Title: "

    def test_compose_webpart_with_text(self):
        """Test composing a text webpart."""
        template_wp = WebPart(
            type="Text",
            webpart_type="Text",
            properties={"content": "<p>{PAGE_CONTENT}</p>"}
        )
        generated_content = {
            "page_content": "<p>Hello World</p>"
        }
        
        webparts = WebPartComposer.compose_webparts(
            [template_wp],
            generated_content
        )
        
        assert len(webparts) == 1
        assert webparts[0].properties["content"] == "<p><p>Hello World</p></p>"

    def test_compose_hero_webpart(self):
        """Test composing a hero webpart."""
        template_wp = WebPart(
            type="Hero",
            webpart_type="Hero",
            properties={
                "title": "{PAGE_TITLE}",
                "description": "{PAGE_DESCRIPTION}",
                "imageSource": "{HERO_IMAGE_URL}"
            }
        )
        generated_content = {
            "hero_title": "Welcome Home",
            "hero_description": "Explore our site",
            "hero_image_url": "https://example.com/image.jpg"
        }
        
        webparts = WebPartComposer.compose_webparts(
            [template_wp],
            generated_content
        )
        
        assert len(webparts) == 1
        assert webparts[0].properties["title"] == "Welcome Home"
        assert webparts[0].properties["description"] == "Explore our site"
        assert webparts[0].properties["imageSource"] == "https://example.com/image.jpg"

    def test_compose_quick_links_webpart(self):
        """Test composing a quick links webpart."""
        template_wp = WebPart(
            type="QuickLinks",
            webpart_type="QuickLinks",
            properties={"items": "{QUICK_LINKS}"}
        )
        generated_content = {
            "quick_links": [
                {"title": "Link 1", "url": "#1"},
                {"title": "Link 2", "url": "#2"}
            ]
        }
        
        webparts = WebPartComposer.compose_webparts(
            [template_wp],
            generated_content
        )
        
        assert len(webparts) == 1
        assert len(webparts[0].properties["items"]) == 2
        assert webparts[0].properties["items"][0]["title"] == "Link 1"

    def test_validate_empty_webparts(self):
        """Test validation of empty webparts list."""
        errors = WebPartComposer.validate_webparts([])
        assert len(errors) > 0
        assert "No webparts" in errors[0]

    def test_validate_valid_webparts(self):
        """Test validation of valid webparts."""
        wp = WebPart(
            type="Text",
            webpart_type="Text",
            properties={"content": "Hello"}
        )
        
        errors = WebPartComposer.validate_webparts([wp])
        assert len(errors) == 0

    def test_compose_multiple_webparts(self):
        """Test composing multiple webparts together."""
        template_webparts = [
            WebPart(
                type="Hero",
                webpart_type="Hero",
                properties={"title": "{PAGE_TITLE}"}
            ),
            WebPart(
                type="Text",
                webpart_type="Text",
                properties={"content": "{PAGE_CONTENT}"}
            )
        ]
        generated_content = {
            "hero_title": "Welcome",
            "page_content": "<p>Content here</p>"
        }
        
        webparts = WebPartComposer.compose_webparts(
            template_webparts,
            generated_content
        )
        
        assert len(webparts) == 2
        assert webparts[0].properties["title"] == "Welcome"
        assert webparts[1].properties["content"] == "<p><p>Content here</p></p>"

    def test_compose_preserves_nonstring_values(self):
        """Test that non-string values are preserved."""
        template_wp = WebPart(
            type="Custom",
            webpart_type="Custom",
            properties={
                "stringProp": "{PAGE_TITLE}",
                "numberProp": 42,
                "boolProp": True
            }
        )
        generated_content = {"hero_title": "Title"}
        
        webparts = WebPartComposer.compose_webparts(
            [template_wp],
            generated_content
        )
        
        assert webparts[0].properties["stringProp"] == "Title"
        assert webparts[0].properties["numberProp"] == 42
        assert webparts[0].properties["boolProp"] is True

    def test_compose_nested_dict_properties(self):
        """Test composing webparts with nested dict properties."""
        template_wp = WebPart(
            type="Custom",
            webpart_type="Custom",
            properties={
                "config": {
                    "title": "{PAGE_TITLE}",
                    "nested": {
                        "description": "{PAGE_DESCRIPTION}"
                    }
                }
            }
        )
        generated_content = {
            "hero_title": "Title",
            "hero_description": "Desc"
        }
        
        webparts = WebPartComposer.compose_webparts(
            [template_wp],
            generated_content
        )
        
        assert webparts[0].properties["config"]["title"] == "Title"
        assert webparts[0].properties["config"]["nested"]["description"] == "Desc"
