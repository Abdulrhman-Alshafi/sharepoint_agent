"""FastAPI application factory and middleware."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from src.infrastructure.rate_limiter import limiter
from src.infrastructure.logging import setup_logging, get_logger
from src.infrastructure.config import settings
from src.infrastructure.correlation import new_correlation_id, set_correlation_id, get_correlation_id
from src.domain.exceptions import DomainException
from src.presentation.api.router import api_router

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate/propagate a unique correlation ID per request.

    If the client sends ``X-Request-ID``, that value is used; otherwise a new
    12-char hex ID is generated.  The ID is stored in ``contextvars`` so it
    appears in every log line and error response automatically.
    """

    async def dispatch(self, request: Request, call_next):
        # Accept an externally provided ID or generate a new one
        incoming_id = request.headers.get("X-Request-ID", "").strip()
        if incoming_id:
            set_correlation_id(incoming_id[:64])  # cap length for safety
        else:
            incoming_id = new_correlation_id()

        response = await call_next(request)
        # Echo the correlation ID back so the frontend can log/display it
        response.headers["X-Request-ID"] = incoming_id
        return response


class UserIdentifierMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract user identifier for rate limiting.
    
    This runs before the rate limiter and stores the user in request.state,
    enabling per-user rate limits instead of global IP-based limits.
    """
    async def dispatch(self, request: Request, call_next):
        # Extract user from Authorization header if present
        auth_header = request.headers.get("Authorization", "")
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            # Try to extract user without full validation (for rate limiting only)
            # Full validation will happen in the get_current_user dependency
            try:
                from src.infrastructure.config import settings
                
                # For JWT tokens, attempt a best-effort decode (no signature
                # verification) to get the user identity for rate-limit bucketing.
                # Full validation happens later in get_current_user dependency.
                try:
                    import base64 as _b64, json as _json
                    parts = token.split(".")
                    if len(parts) == 3:
                        padding = 4 - len(parts[1]) % 4
                        payload_json = _b64.urlsafe_b64decode(parts[1] + "=" * padding)
                        claims = _json.loads(payload_json)
                        user = claims.get("upn") or claims.get("email") or claims.get("preferred_username")
                        if user:
                            request.state.current_user = user
                except Exception:
                    pass  # Rate limiter will fall back to IP
            except Exception as e:
                # If anything fails, user will be rate limited by IP (fallback in limiter)
                logger.warning("Auth middleware failed to identify user: %s", e)
        
        response = await call_next(request)
        return response


def create_app() -> FastAPI:
    """Factory function to create and configure FastAPI application."""
    # Validate configuration first
    try:
        settings.validate()
    except ValueError as e:
        logger.error("Configuration validation failed: %s", e)
        raise
    
    # Setup logging
    setup_logging(log_level=settings.LOG_LEVEL, environment="production")
    logger.info("Starting SharePoint AI Agent in production mode")
    
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Execute startup logic: load AI models and pre-warm Graph connection."""
        logger.info("Starting SharePoint AI API...")
        # 1. Initialize ServiceContainer (singleton)
        # 2. Graph API validation is skipped during startup (no user context)
        # The first authenticated request will validate MS Graph connectivity.
        # This avoids attempting OBO flow without a valid user token.

        # Phase 4: Run OntologyExpander once at startup to load custom ontology
        try:
            from src.infrastructure.services.ontology_expander import OntologyExpander
            _promoted = await OntologyExpander().expand()
            if _promoted:
                logger.info("OntologyExpander promoted %d new phrases at startup", _promoted)
        except Exception as _oe_exc:
            logger.warning("OntologyExpander startup run failed (non-fatal): %s", _oe_exc)

        yield
        logger.info("Shutting down SharePoint AI API...")

    app = FastAPI(
        title="SharePoint AI Agent",
        description="Clean Architecture backend for SharePoint AI Agent (DDD/CA)",
        version="2.0.0",
        lifespan=lifespan
    )

    # -----------------------------------------------------------------------
    # Correlation ID Middleware — must run FIRST (outermost)
    # -----------------------------------------------------------------------
    # Generates/propagates X-Request-ID for end-to-end tracing
    app.add_middleware(CorrelationIdMiddleware)

    # -----------------------------------------------------------------------
    # User Identifier Middleware - Extract user for rate limiting
    # -----------------------------------------------------------------------
    # Must run BEFORE rate limiting to populate request.state.current_user
    app.add_middleware(UserIdentifierMiddleware)

    # -----------------------------------------------------------------------
    # CORS Configuration - Tenant-bound for SharePoint
    # -----------------------------------------------------------------------
    # Parse allowed origins from configuration
    allowed_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # Build tenant-specific SharePoint origins when configured
    cors_kwargs = {
        "allow_origins": allowed_origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": ["Authorization", "Content-Type", "Accept"],
        "expose_headers": ["X-Request-ID"],
        "max_age": 3600,
    }

    if settings.ALLOWED_SHAREPOINT_TENANTS:
        # Strict mode: only explicitly listed tenants are accepted
        tenant_names = [
            t.strip() for t in settings.ALLOWED_SHAREPOINT_TENANTS.split(",")
            if t.strip()
        ]
        tenant_origins = [f"https://{t}.sharepoint.com" for t in tenant_names]
        cors_kwargs["allow_origins"] = allowed_origins + tenant_origins
        logger.info(
            "CORS: tenant-bound mode — allowed SharePoint origins: %s",
            tenant_origins,
        )
    else:
        # Fallback: allow all SharePoint subdomains (less secure, logged warning)
        cors_kwargs["allow_origin_regex"] = r"https://[\w-]+\.sharepoint\.com"
        logger.warning(
            "CORS: using broad regex for SharePoint origins. "
            "Set ALLOWED_SHAREPOINT_TENANTS for stricter validation."
        )

    app.add_middleware(CORSMiddleware, **cors_kwargs)

    # -----------------------------------------------------------------------
    # Security store status
    # -----------------------------------------------------------------------
    from src.infrastructure.services.redis_security_store import security_store
    if security_store.is_distributed:
        logger.info("SecurityStore: distributed mode (Redis)")
    else:
        logger.warning(
            "SecurityStore: in-memory mode — rate limits, auth blocks, and "
            "OBO cache will NOT persist across restarts or scale to multiple pods."
        )

    # -----------------------------------------------------------------------
    # Attach rate limiter state & 429 error handler
    # -----------------------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -----------------------------------------------------------------------
    # Domain Exception Handlers - Consistent error responses
    # -----------------------------------------------------------------------
    
    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException):
        """Handle all domain exceptions with consistent error response format."""
        logger.warning(
            "Domain exception occurred: %s - %s", exc.error_code, exc.message,
            extra={"error_code": exc.error_code, "details": exc.details}
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
            headers={"X-Request-ID": get_correlation_id()},
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle validation errors from configuration or input."""
        logger.error("ValueError: %s", str(exc))
        cid = get_correlation_id()
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_VALUE",
                    "message": str(exc),
                    "details": {},
                    "recovery_hint": "Please check your input and try again.",
                    "correlation_id": cid,
                }
            },
            headers={"X-Request-ID": cid},
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Catch-all handler for unexpected exceptions."""
        logger.error(
            "Unhandled exception: %s: %s", exc.__class__.__name__, str(exc),
            exc_info=True
        )
        cid = get_correlation_id()
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                    "details": {
                        "type": exc.__class__.__name__
                    },
                    "recovery_hint": "If this persists, please contact your administrator.",
                    "correlation_id": cid,
                }
            },
            headers={"X-Request-ID": cid},
        )

    # Include routers
    app.include_router(api_router, prefix="/api/v1")

    # Enhanced health check endpoint
    @app.get("/health", tags=["Health"])
    @app.get("/api/v1/health", tags=["Health"])
    async def health_check():
        """
        Minimal health check for Kubernetes probes and monitoring.
        Verifies critical services without leaking internal details.
        """
        health_status = {
            "status": "healthy",
            "services": {}
        }
        
        # Check Graph API connectivity
        try:
            from src.presentation.api import ServiceContainer
            repo = ServiceContainer.get_sharepoint_repository()
            graph_client = repo.graph_client
            await graph_client.get("/sites?search=*&$top=1")
            health_status["services"]["graph_api"] = "healthy"
        except Exception as e:
            logger.warning("Health check: Graph API unhealthy: %s", e)
            health_status["services"]["graph_api"] = "unhealthy"
            health_status["status"] = "degraded"
        
        # Check AI provider connectivity (don't reveal which provider)
        try:
            from src.infrastructure.config import settings
            ai_provider = settings.AI_PROVIDER
            if ai_provider == "gemini":
                if not settings.GEMINI_API_KEY:
                    raise ValueError("API key not configured")
            elif ai_provider == "openai":
                if not settings.OPENAI_API_KEY:
                    raise ValueError("API key not configured")
            elif ai_provider == "vertexai":
                if not settings.VERTEXAI_PROJECT_ID:
                    raise ValueError("Project not configured")
            health_status["services"]["ai_provider"] = "healthy"
        except Exception as e:
            logger.warning("Health check: AI provider unhealthy: %s", e)
            health_status["services"]["ai_provider"] = "unhealthy"
            health_status["status"] = "degraded"
        
        # Check SharePoint site accessibility (don't leak SITE_ID)
        try:
            from src.infrastructure.config import settings
            if settings.SITE_ID:
                from src.presentation.api import ServiceContainer
                repo = ServiceContainer.get_sharepoint_repository()
                graph_client = repo.graph_client
                await graph_client.get(f"/sites/{settings.SITE_ID}")
                health_status["services"]["sharepoint_site"] = "healthy"
            else:
                health_status["services"]["sharepoint_site"] = "not configured"
        except Exception as e:
            logger.warning("Health check: SharePoint site unhealthy: %s", e)
            health_status["services"]["sharepoint_site"] = "unhealthy"
            health_status["status"] = "degraded"
        
        return health_status

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "SharePoint AI Agent",
            "docs": "/docs"
        }

    return app


app = create_app()
