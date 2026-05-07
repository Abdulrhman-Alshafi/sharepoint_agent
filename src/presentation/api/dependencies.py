"""FastAPI dependencies for authentication and authorization."""

import logging
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from src.infrastructure.services.token_validation_service import TokenValidationService
from src.infrastructure.services.redis_security_store import security_store
from src.domain.exceptions import AuthenticationException

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(auto_error=False, tokenUrl="token")
_token_validator = TokenValidationService()

# ---------------------------------------------------------------------------
# IP-based auth failure rate limiter
# Uses the distributed SecurityStore (Redis or in-memory fallback).
# Blocks an IP for AUTH_BLOCK_SECONDS after AUTH_MAX_FAILURES failed attempts
# within AUTH_WINDOW_SECONDS.
# ---------------------------------------------------------------------------
_AUTH_MAX_FAILURES  = 10   # max failures allowed in the window
_AUTH_WINDOW_SECONDS = 60  # rolling window (seconds)
_AUTH_BLOCK_SECONDS = 300  # block duration after threshold exceeded (5 min)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_auth_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded the auth failure threshold."""
    # Check if still blocked
    is_blocked, retry_after = security_store.is_ip_blocked(ip)
    if is_blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Check failure count within rolling window
    failure_count = security_store.get_auth_failure_count(ip, _AUTH_WINDOW_SECONDS)
    if failure_count >= _AUTH_MAX_FAILURES:
        security_store.block_ip(ip, _AUTH_BLOCK_SECONDS)
        logger.warning(f"IP {ip} blocked for {_AUTH_BLOCK_SECONDS}s after {_AUTH_MAX_FAILURES} auth failures")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts. Try again later.",
            headers={"Retry-After": str(_AUTH_BLOCK_SECONDS)},
        )


def _record_auth_failure(ip: str) -> None:
    security_store.record_auth_failure(ip)


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> str:
    """FastAPI dependency to extract and validate the user identity from a Bearer token.

    Returns:
        The user_email / UPN of the authentic requester.

    Raises:
        HTTPException: If token is missing, invalid, or IP is rate-limited.
    """
    # OBO authentication requires a user token.
    # All Graph calls run on-behalf-of the authenticated user,
    # so a Bearer token is mandatory.
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Bearer token missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ip = _get_client_ip(request)
    _check_auth_rate_limit(ip)

    # Then try JWT validation (Azure AD token)
    logger.debug(f"[get_current_user] Validating token from IP {ip}. Token length: {len(token) if token else 0}")
    try:
        payload = await _token_validator.validate_token(token)
        identity = _token_validator.extract_user_identity(payload)
        logger.info(f"Authenticated: {identity}")
        logger.debug(f"[get_current_user] Token validated successfully for {identity}")
        return identity
    except AuthenticationException as e:
        _record_auth_failure(ip)
        logger.warning(f"Auth failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_token(request: Request, token: str = Depends(oauth2_scheme)) -> str:
    """FastAPI dependency to get the validated raw bearer token.

    Returns:
        The raw bearer token for OBO (on-behalf-of) authentication.

    Raises:
        HTTPException: If token is missing, invalid, or IP is rate-limited.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Bearer token missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ip = _get_client_ip(request)
    _check_auth_rate_limit(ip)

    logger.debug(f"[get_current_user_token] Validating token from IP {ip}. Token length: {len(token) if token else 0}")
    try:
        payload = await _token_validator.validate_token(token)
        identity = _token_validator.extract_user_identity(payload)
        logger.debug(f"[get_current_user_token] Token validated successfully for {identity}")
        return token  # Return the raw token for OBO authentication
    except AuthenticationException as e:
        _record_auth_failure(ip)
        logger.warning(f"Auth failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
