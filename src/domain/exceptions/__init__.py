"""Domain-level exceptions for SharePoint provisioning."""

from typing import Optional, Dict, Any, List


class DomainException(Exception):
    """Base exception for all domain exceptions.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error details/context
        http_status: Suggested HTTP status code for API responses
        recovery_hint: User-friendly suggestion for resolving the error
        error_category: High-level category (auth, permission, validation, service, internal)
    """
    
    def __init__(
        self, 
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        http_status: int = 500,
        recovery_hint: Optional[str] = None,
        error_category: str = "internal",
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.http_status = http_status
        self.recovery_hint = recovery_hint
        self.error_category = error_category
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        from src.infrastructure.correlation import get_correlation_id
        result: Dict[str, Any] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }
        if self.recovery_hint:
            result["error"]["recovery_hint"] = self.recovery_hint
        cid = get_correlation_id()
        if cid:
            result["error"]["correlation_id"] = cid
        return result


class InvalidBlueprintException(DomainException):
    """Raised when a provisioning blueprint is invalid."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="INVALID_BLUEPRINT",
            details=details,
            http_status=422,
            recovery_hint="Try rephrasing your request with clearer requirements.",
            error_category="validation",
        )


class SharePointProvisioningException(DomainException):
    """Raised when SharePoint provisioning fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="PROVISIONING_FAILED",
            details=details,
            http_status=500,
            recovery_hint="Please try again. If the problem persists, check your SharePoint site permissions.",
            error_category="service",
        )


class BlueprintGenerationException(DomainException):
    """Raised when AI blueprint generation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="BLUEPRINT_GENERATION_FAILED",
            details=details,
            http_status=500,
            recovery_hint="The AI service had trouble processing your request. Try rephrasing or simplifying it.",
            error_category="service",
        )


class RepositoryException(DomainException):
    """Raised when repository operations fail."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="REPOSITORY_ERROR",
            details=details,
            http_status=500,
            recovery_hint="There was a problem accessing SharePoint data. Please try again.",
            error_category="service",
        )


class DataQueryException(DomainException):
    """Raised when data intelligence query fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="DATA_QUERY_FAILED",
            details=details,
            http_status=500,
            recovery_hint="Try rephrasing your question or specifying the list/library name more clearly.",
            error_category="service",
        )


class HighRiskBlueprintException(DomainException):
    """Raised when a provisioning request is valid but carries high risk."""
    
    def __init__(self, warnings: list, original_prompt: str):
        self.warnings = warnings
        self.original_prompt = original_prompt
        warning_text = " | ".join(warnings)
        super().__init__(
            message=f"High risk detected: {warning_text}",
            error_code="HIGH_RISK_BLUEPRINT",
            details={"warnings": warnings, "original_prompt": original_prompt},
            http_status=422,
            recovery_hint="Type 'yes' to confirm, or rephrase your request to cancel.",
            error_category="validation",
        )


class PermissionDeniedException(DomainException):
    """Raised when the requesting user lacks sufficient permissions for the operation."""
    
    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="PERMISSION_DENIED",
            details=details,
            http_status=403,
            recovery_hint="Contact your SharePoint administrator to request the necessary access.",
            error_category="permission",
        )


class AuthenticationException(DomainException):
    """Raised when the user fails to provide a valid, authentic JWT token."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            details=details,
            http_status=401,
            recovery_hint="Please refresh the page and sign in again.",
            error_category="auth",
        )


class ConfigurationError(DomainException):
    """Raised when application configuration is invalid or missing."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details,
            http_status=500,
            recovery_hint="Check your .env file and ensure all required environment variables are set.",
            error_category="internal",
        )


class AIProviderError(DomainException):
    """Raised when AI provider (Gemini/OpenAI/etc.) fails."""
    
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if provider:
            error_details["provider"] = provider
        super().__init__(
            message=message,
            error_code="AI_PROVIDER_ERROR",
            details=error_details,
            http_status=500,
            recovery_hint="The AI service is temporarily unavailable. Please try again in a moment.",
            error_category="service",
        )


class SharePointAPIError(DomainException):
    """Raised when SharePoint/Graph API calls fail."""
    
    def __init__(
        self, 
        message: str, 
        status_code: Optional[int] = None,
        endpoint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if status_code:
            error_details["status_code"] = status_code
        if endpoint:
            error_details["endpoint"] = endpoint
        super().__init__(
            message=message,
            error_code="SHAREPOINT_API_ERROR",
            details=error_details,
            http_status=502,  # Bad Gateway - external service error
            recovery_hint="SharePoint is having trouble responding. Please try again in a moment.",
            error_category="service",
        )


class DomainValidationError(DomainException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=error_details,
            http_status=400,
            recovery_hint="Please check your input and try again.",
            error_category="validation",
        )


# Backwards-compatible alias — prefer DomainValidationError in new code
ValidationError = DomainValidationError


class ResourceNotFoundError(DomainException):
    """Raised when a requested resource is not found."""
    
    def __init__(self, resource_type: str, resource_id: str, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        error_details["resource_type"] = resource_type
        error_details["resource_id"] = resource_id
        super().__init__(
            message=f"{resource_type} with ID '{resource_id}' not found",
            error_code="RESOURCE_NOT_FOUND",
            details=error_details,
            http_status=404,
            recovery_hint="Check that the resource name is correct and that you have access to it.",
            error_category="validation",
        )


# ── New exception types for transient infrastructure failures ──────────────


class RateLimitError(DomainException):
    """Raised when an external service rate-limits us (HTTP 429)."""
    
    def __init__(
        self,
        service: str = "external service",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        error_details = details or {}
        error_details["service"] = service
        if retry_after:
            error_details["retry_after_seconds"] = retry_after
        hint = f"Please wait {retry_after} seconds and try again." if retry_after else "Please wait a moment and try again."
        super().__init__(
            message=f"{service} is rate-limiting requests. Please slow down.",
            error_code="RATE_LIMITED",
            details=error_details,
            http_status=429,
            recovery_hint=hint,
            error_category="service",
        )


class ExternalServiceUnavailableError(DomainException):
    """Raised when an external service (Graph API, AI, etc.) is temporarily unavailable."""
    
    def __init__(
        self,
        service: str = "external service",
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        error_details["service"] = service
        super().__init__(
            message=f"{service} is temporarily unavailable.",
            error_code="SERVICE_UNAVAILABLE",
            details=error_details,
            http_status=503,
            recovery_hint="The service should recover shortly. Please try again in a minute.",
            error_category="service",
        )


class ExternalTimeoutError(DomainException):
    """Raised when an external service call exceeds the deadline."""
    
    def __init__(
        self,
        service: str = "external service",
        timeout_seconds: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        error_details["service"] = service
        if timeout_seconds:
            error_details["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=f"{service} took too long to respond.",
            error_code="TIMEOUT",
            details=error_details,
            http_status=504,
            recovery_hint="The service is slow right now. Try again or simplify your request.",
            error_category="service",
        )


class CircuitBreakerOpenError(DomainException):
    """Raised when the circuit breaker prevents calls to a failing service."""
    
    def __init__(
        self,
        service: str = "external service",
        recovery_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        error_details = details or {}
        error_details["service"] = service
        if recovery_seconds:
            error_details["recovery_seconds"] = recovery_seconds
        hint = f"{service} is temporarily disabled due to repeated failures. It will be retried in {recovery_seconds}s." if recovery_seconds else f"{service} is temporarily disabled. Please try again shortly."
        super().__init__(
            message=f"{service} is currently unavailable due to repeated failures.",
            error_code="CIRCUIT_BREAKER_OPEN",
            details=error_details,
            http_status=503,
            recovery_hint=hint,
            error_category="service",
        )
