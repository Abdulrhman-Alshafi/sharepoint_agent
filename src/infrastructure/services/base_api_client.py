"""Base HTTP API client using httpx.AsyncClient.

Replaces the previous requests.Session-based implementation so that all HTTP
I/O is non-blocking and compatible with FastAPI's async event loop.
"""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from src.infrastructure.services.authentication_service import AuthenticationService


class BaseAPIClient:
    """Shared base for all async HTTP API clients.

    Provides:
    - A configured :class:`httpx.AsyncClient` with automatic transport-level
      retries on network errors.
    - Storage of ``auth_service`` and ``site_id`` used by all subclasses.

    Subclasses implement async ``get`` / ``post`` / ``patch`` / ``delete``
    methods that build absolute URLs and call ``await self.http.<method>(...)``.
    """

    #: Total number of retry attempts before giving up.
    TOTAL_RETRIES: int = 5
    #: HTTP status codes that trigger a retry.
    RETRY_ON_STATUS = [429, 503, 504]
    #: Exponential back-off multiplier (seconds).
    BACKOFF_FACTOR: int = 1
    #: Request timeout (seconds) — used by the async httpx client.
    TIMEOUT: float = 60.0

    def __init__(self, auth_service: AuthenticationService, site_id: str) -> None:
        """Initialise the client.

        Args:
            auth_service: Provides access tokens / request headers.
            site_id: SharePoint site identifier used to build API endpoints.
        """
        self.auth_service = auth_service
        self.site_id = site_id

    # ── Private helpers ──────────────────────────────────────────────────────


    def _build_client(self) -> httpx.AsyncClient:
        """Create and return an :class:`httpx.AsyncClient` with retry transport."""
        transport = httpx.AsyncHTTPTransport(retries=self.TOTAL_RETRIES)
        return httpx.AsyncClient(
            transport=transport,
            timeout=self.TIMEOUT,
            follow_redirects=True,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(lambda e: getattr(getattr(e, 'response', None), 'status_code', 0) in {429, 503, 504})
    )
    async def _request(self, method: str, url: str, **kwargs):
        async with self._build_client() as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
