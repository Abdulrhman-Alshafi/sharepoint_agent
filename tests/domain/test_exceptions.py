"""Tests for all 14 domain exception classes."""

import pytest
from src.domain.exceptions import (
    DomainException,
    InvalidBlueprintException,
    SharePointProvisioningException,
    BlueprintGenerationException,
    RepositoryException,
    DataQueryException,
    HighRiskBlueprintException,
    PermissionDeniedException,
    AuthenticationException,
    ConfigurationError,
    AIProviderError,
    SharePointAPIError,
    ValidationError,
    ResourceNotFoundError,
)


class TestDomainException:
    def test_basic_instantiation(self):
        exc = DomainException("Something went wrong")
        assert str(exc) == "Something went wrong"
        assert exc.message == "Something went wrong"
        assert exc.http_status == 500

    def test_default_error_code_is_class_name(self):
        exc = DomainException("msg")
        assert exc.error_code == "DomainException"

    def test_custom_error_code(self):
        exc = DomainException("msg", error_code="MY_CODE")
        assert exc.error_code == "MY_CODE"

    def test_details_default_to_empty_dict(self):
        exc = DomainException("msg")
        assert exc.details == {}

    def test_custom_details(self):
        exc = DomainException("msg", details={"key": "value"})
        assert exc.details == {"key": "value"}

    def test_to_dict_structure(self):
        exc = DomainException("msg", error_code="TEST_CODE", details={"x": 1})
        d = exc.to_dict()
        assert "error" in d
        assert d["error"]["code"] == "TEST_CODE"
        assert d["error"]["message"] == "msg"
        assert d["error"]["details"] == {"x": 1}

    def test_is_exception_subclass(self):
        exc = DomainException("msg")
        assert isinstance(exc, Exception)


class TestInvalidBlueprintException:
    def test_http_status(self):
        exc = InvalidBlueprintException("Bad blueprint")
        assert exc.http_status == 422

    def test_error_code(self):
        exc = InvalidBlueprintException("Bad blueprint")
        assert exc.error_code == "INVALID_BLUEPRINT"

    def test_to_dict(self):
        exc = InvalidBlueprintException("Bad blueprint", details={"field": "lists"})
        d = exc.to_dict()
        assert d["error"]["code"] == "INVALID_BLUEPRINT"
        assert d["error"]["details"]["field"] == "lists"


class TestSharePointProvisioningException:
    def test_http_status(self):
        exc = SharePointProvisioningException("Failed")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = SharePointProvisioningException("Failed")
        assert exc.error_code == "PROVISIONING_FAILED"


class TestBlueprintGenerationException:
    def test_http_status(self):
        exc = BlueprintGenerationException("AI failed")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = BlueprintGenerationException("AI failed")
        assert exc.error_code == "BLUEPRINT_GENERATION_FAILED"


class TestRepositoryException:
    def test_http_status(self):
        exc = RepositoryException("DB error")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = RepositoryException("DB error")
        assert exc.error_code == "REPOSITORY_ERROR"


class TestDataQueryException:
    def test_http_status(self):
        exc = DataQueryException("Query failed")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = DataQueryException("Query failed")
        assert exc.error_code == "DATA_QUERY_FAILED"


class TestHighRiskBlueprintException:
    def test_http_status(self):
        exc = HighRiskBlueprintException(warnings=["Irreversible"], original_prompt="delete all")
        assert exc.http_status == 422

    def test_error_code(self):
        exc = HighRiskBlueprintException(warnings=["Irreversible"], original_prompt="delete all")
        assert exc.error_code == "HIGH_RISK_BLUEPRINT"

    def test_warnings_stored(self):
        warnings = ["Will delete 500 items", "Irreversible"]
        exc = HighRiskBlueprintException(warnings=warnings, original_prompt="delete all")
        assert exc.warnings == warnings

    def test_original_prompt_in_details(self):
        exc = HighRiskBlueprintException(warnings=["W"], original_prompt="bad prompt")
        assert exc.details["original_prompt"] == "bad prompt"

    def test_warnings_in_details(self):
        exc = HighRiskBlueprintException(warnings=["W1", "W2"], original_prompt="p")
        assert exc.details["warnings"] == ["W1", "W2"]

    def test_message_includes_warnings(self):
        exc = HighRiskBlueprintException(warnings=["Too risky"], original_prompt="p")
        assert "Too risky" in exc.message


class TestPermissionDeniedException:
    def test_http_status(self):
        exc = PermissionDeniedException()
        assert exc.http_status == 403

    def test_error_code(self):
        exc = PermissionDeniedException()
        assert exc.error_code == "PERMISSION_DENIED"

    def test_default_message(self):
        exc = PermissionDeniedException()
        assert "Insufficient permissions" in exc.message

    def test_custom_message(self):
        exc = PermissionDeniedException("You cannot delete this site")
        assert exc.message == "You cannot delete this site"


class TestAuthenticationException:
    def test_http_status(self):
        exc = AuthenticationException()
        assert exc.http_status == 401

    def test_error_code(self):
        exc = AuthenticationException()
        assert exc.error_code == "AUTHENTICATION_FAILED"

    def test_default_message(self):
        exc = AuthenticationException()
        assert "Authentication failed" in exc.message


class TestConfigurationError:
    def test_http_status(self):
        exc = ConfigurationError("Missing env var")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = ConfigurationError("Missing env var")
        assert exc.error_code == "CONFIGURATION_ERROR"


class TestAIProviderError:
    def test_http_status(self):
        exc = AIProviderError("Gemini timeout")
        assert exc.http_status == 500

    def test_error_code(self):
        exc = AIProviderError("Timeout")
        assert exc.error_code == "AI_PROVIDER_ERROR"

    def test_provider_in_details(self):
        exc = AIProviderError("Quota exceeded", provider="gemini")
        assert exc.details["provider"] == "gemini"

    def test_no_provider_still_works(self):
        exc = AIProviderError("Timeout")
        assert "provider" not in exc.details


class TestSharePointAPIError:
    def test_http_status(self):
        exc = SharePointAPIError("Not found")
        assert exc.http_status == 502

    def test_error_code(self):
        exc = SharePointAPIError("Not found")
        assert exc.error_code == "SHAREPOINT_API_ERROR"

    def test_status_code_in_details(self):
        exc = SharePointAPIError("Forbidden", status_code=403)
        assert exc.details["status_code"] == 403

    def test_endpoint_in_details(self):
        exc = SharePointAPIError("Error", endpoint="/v1.0/sites")
        assert exc.details["endpoint"] == "/v1.0/sites"

    def test_none_status_code_not_in_details(self):
        exc = SharePointAPIError("Error")
        assert "status_code" not in exc.details


class TestValidationError:
    def test_http_status(self):
        exc = ValidationError("Invalid value")
        assert exc.http_status == 400

    def test_error_code(self):
        exc = ValidationError("Invalid value")
        assert exc.error_code == "VALIDATION_ERROR"

    def test_field_in_details(self):
        exc = ValidationError("Too short", field="title")
        assert exc.details["field"] == "title"

    def test_no_field_still_works(self):
        exc = ValidationError("Invalid")
        assert "field" not in exc.details


class TestResourceNotFoundError:
    def test_http_status(self):
        exc = ResourceNotFoundError("List", "abc-123")
        assert exc.http_status == 404

    def test_error_code(self):
        exc = ResourceNotFoundError("List", "abc-123")
        assert exc.error_code == "RESOURCE_NOT_FOUND"

    def test_message_format(self):
        exc = ResourceNotFoundError("List", "abc-123")
        assert "List" in exc.message
        assert "abc-123" in exc.message

    def test_details_contain_type_and_id(self):
        exc = ResourceNotFoundError("Page", "page-456")
        assert exc.details["resource_type"] == "Page"
        assert exc.details["resource_id"] == "page-456"
