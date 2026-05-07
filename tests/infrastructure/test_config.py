"""Tests for Settings.validate() — all branches."""

import pytest
from src.infrastructure.config import Settings


def _make_settings(**kwargs):
    return Settings(**kwargs)


def _valid_base():
    """Minimum valid settings (Gemini provider)."""
    return dict(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="test-key",
        TENANT_ID="tenant-id",
        CLIENT_ID="client-id",
        CLIENT_SECRET="client-secret",
        SITE_ID="site-id",
        ENVIRONMENT="development",
        DEV_MODE=False,
        LOG_LEVEL="INFO",
    )


class TestSettingsValidate:
    def test_valid_gemini_config_passes(self):
        s = _make_settings(**_valid_base())
        s.validate()  # Should not raise

    def test_gemini_missing_api_key_raises(self):
        overrides = {**_valid_base(), "AI_PROVIDER": "gemini", "GEMINI_API_KEY": ""}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="GEMINI_API_KEY"):

            _make_settings(**overrides)

    def test_vertexai_missing_project_id_raises(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "vertexai",
            "VERTEXAI_PROJECT_ID": "",
            "VERTEXAI_CREDENTIALS_PATH": "/path/to/creds.json",
        }
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="VERTEXAI_PROJECT_ID"):

            _make_settings(**overrides)

    def test_vertexai_missing_credentials_path_raises(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "vertexai",
            "VERTEXAI_PROJECT_ID": "my-project",
            "VERTEXAI_CREDENTIALS_PATH": "",
        }
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="VERTEXAI_CREDENTIALS_PATH"):

            _make_settings(**overrides)

    def test_vertexai_valid_passes(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "vertexai",
            "VERTEXAI_PROJECT_ID": "my-project",
            "VERTEXAI_CREDENTIALS_PATH": "/path/to/creds.json",
        }
        s = _make_settings(**overrides)
        s.validate()  # Should not raise

    def test_openai_missing_api_key_raises(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "http://localhost:11434/v1",
        }
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="OPENAI_API_KEY"):

            _make_settings(**overrides)

    def test_openai_missing_base_url_raises(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "",
        }
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="OPENAI_BASE_URL"):

            _make_settings(**overrides)

    def test_openai_valid_passes(self):
        overrides = {
            **_valid_base(),
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "http://localhost:11434/v1",
        }
        s = _make_settings(**overrides)
        s.validate()  # Should not raise

    def test_missing_tenant_id_raises(self):
        overrides = {**_valid_base(), "TENANT_ID": ""}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="TENANT_ID"):

            _make_settings(**overrides)

    def test_missing_client_id_raises(self):
        overrides = {**_valid_base(), "CLIENT_ID": ""}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="CLIENT_ID"):

            _make_settings(**overrides)

    def test_missing_client_secret_raises(self):
        overrides = {**_valid_base(), "CLIENT_SECRET": ""}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="CLIENT_SECRET"):

            _make_settings(**overrides)

    def test_missing_site_id_raises(self):
        overrides = {**_valid_base(), "SITE_ID": ""}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="SITE_ID"):

            _make_settings(**overrides)

    def test_invalid_environment_raises(self):
        overrides = {**_valid_base(), "ENVIRONMENT": "sandbox"}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="ENVIRONMENT"):

            _make_settings(**overrides)

    def test_dev_mode_in_production_raises(self):
        overrides = {**_valid_base(), "DEV_MODE": True, "ENVIRONMENT": "production"}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="DEV_MODE"):

            _make_settings(**overrides)

    def test_dev_mode_in_development_is_fine(self):
        overrides = {**_valid_base(), "DEV_MODE": True, "ENVIRONMENT": "development"}
        s = _make_settings(**overrides)
        s.validate()  # Should not raise

    def test_invalid_log_level_raises(self):
        overrides = {**_valid_base(), "LOG_LEVEL": "VERBOSE"}
        with pytest.raises((ValueError, __import__("pydantic").ValidationError), match="LOG_LEVEL"):

            _make_settings(**overrides)

    @pytest.mark.parametrize("env", ["development", "staging", "production"])
    def test_all_valid_environments_pass(self, env):
        overrides = {**_valid_base(), "ENVIRONMENT": env}
        if env == "production":
            overrides["DEV_MODE"] = False
        s = _make_settings(**overrides)
        s.validate()  # Should not raise

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_all_valid_log_levels_pass(self, level):
        overrides = {**_valid_base(), "LOG_LEVEL": level}
        s = _make_settings(**overrides)
        s.validate()  # Should not raise
