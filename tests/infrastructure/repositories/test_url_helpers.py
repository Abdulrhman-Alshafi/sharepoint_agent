"""Tests for URLHelpers utility class."""

import pytest
from unittest.mock import MagicMock
from src.infrastructure.repositories.utils.url_helpers import URLHelpers
from src.domain.exceptions import SharePointProvisioningException


class TestGeneratePageName:
    def test_basic_title(self):
        result = URLHelpers.generate_page_name("My Home Page")
        assert result == "my-home-page.aspx"

    def test_special_characters_stripped(self):
        result = URLHelpers.generate_page_name("Hello! World?")
        assert "!" not in result
        assert "?" not in result

    def test_ends_with_aspx(self):
        result = URLHelpers.generate_page_name("About Us")
        assert result.endswith(".aspx")

    def test_already_ends_with_aspx(self):
        result = URLHelpers.generate_page_name("home.aspx")
        # Should not have double .aspx
        assert result.count(".aspx") == 1

    def test_uppercase_lowercased(self):
        result = URLHelpers.generate_page_name("HELLO WORLD")
        assert result == result.lower()

    def test_multiple_spaces_collapsed_to_hyphen(self):
        result = URLHelpers.generate_page_name("Hello   World")
        assert "--" not in result
        assert " " not in result

    def test_leading_trailing_whitespace_stripped(self):
        result = URLHelpers.generate_page_name("  Home Page  ")
        assert not result.startswith("-")


class TestGetSiteBaseUrl:
    def test_returns_cached_url_immediately(self):
        session = MagicMock()
        result = URLHelpers.get_site_base_url(
            site_id="site-123",
            http_session=session,
            headers={},
            cached_url="https://contoso.sharepoint.com",
        )
        assert result == "https://contoso.sharepoint.com"
        session.get.assert_not_called()

    def test_queries_graph_api_when_no_cache(self):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"webUrl": "https://contoso.sharepoint.com"}
        session.get.return_value = mock_response

        result = URLHelpers.get_site_base_url(
            site_id="site-123",
            http_session=session,
            headers={"Authorization": "Bearer token"},
        )
        assert result == "https://contoso.sharepoint.com"

    def test_raises_when_api_call_fails(self):
        session = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = False
        session.get.return_value = mock_response

        with pytest.raises(SharePointProvisioningException):
            URLHelpers.get_site_base_url(
                site_id="site-123",
                http_session=session,
                headers={},
            )
