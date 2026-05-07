"""Tests for TokenValidationService."""

import pytest
from unittest.mock import MagicMock, patch
import jwt

from src.domain.exceptions import AuthenticationException


def _make_service():
    with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient"):
        from src.infrastructure.services.token_validation_service import TokenValidationService
        svc = TokenValidationService()
    return svc


class TestValidateToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        mock_payload = {"upn": "user@contoso.com", "sub": "abc123"}
        mock_signing_key = MagicMock()

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient") as MockClient:
            instance = MockClient.return_value
            instance.get_signing_key_from_jwt.return_value = mock_signing_key

            with patch("src.infrastructure.services.token_validation_service.jwt.decode") as mock_decode:
                mock_decode.return_value = mock_payload
                svc = TokenValidationService()
                result = await svc.validate_token("valid.jwt.token")

        assert result == mock_payload

    @pytest.mark.asyncio
    async def test_expired_token_raises_authentication_exception(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient") as MockClient:
            instance = MockClient.return_value
            instance.get_signing_key_from_jwt.return_value = MagicMock()

            with patch("src.infrastructure.services.token_validation_service.jwt.decode") as mock_decode:
                mock_decode.side_effect = jwt.exceptions.ExpiredSignatureError()
                svc = TokenValidationService()

                with pytest.raises(AuthenticationException, match="expired"):
                    await svc.validate_token("expired.jwt.token")

    @pytest.mark.asyncio
    async def test_malformed_token_raises_authentication_exception(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient") as MockClient:
            instance = MockClient.return_value
            instance.get_signing_key_from_jwt.return_value = MagicMock()

            with patch("src.infrastructure.services.token_validation_service.jwt.decode") as mock_decode:
                mock_decode.side_effect = jwt.exceptions.DecodeError("bad token")
                svc = TokenValidationService()

                with pytest.raises(AuthenticationException, match="malformed"):
                    await svc.validate_token("bad.token")

    @pytest.mark.asyncio
    async def test_jwks_fetch_fails_raises_authentication_exception(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient") as MockClient:
            instance = MockClient.return_value
            instance.get_signing_key_from_jwt.side_effect = jwt.exceptions.PyJWKClientError("network")
            svc = TokenValidationService()

            with pytest.raises(AuthenticationException, match="signing keys"):
                await svc.validate_token("any.jwt.token")

    @pytest.mark.asyncio
    async def test_unexpected_exception_raises_authentication_exception(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient") as MockClient:
            instance = MockClient.return_value
            instance.get_signing_key_from_jwt.side_effect = RuntimeError("boom")
            svc = TokenValidationService()

            with pytest.raises(AuthenticationException):
                await svc.validate_token("any.jwt.token")


class TestExtractUserIdentity:
    def _make_svc(self):
        from src.infrastructure.services.token_validation_service import TokenValidationService

        with patch("src.infrastructure.services.token_validation_service.jwt.PyJWKClient"):
            return TokenValidationService()

    @pytest.mark.asyncio
    async def test_extracts_upn(self):
        svc = self._make_svc()
        payload = {"upn": "alice@contoso.com"}
        assert svc.extract_user_identity(payload) == "alice@contoso.com"

    @pytest.mark.asyncio
    async def test_falls_back_to_preferred_username(self):
        svc = self._make_svc()
        payload = {"preferred_username": "bob@contoso.com"}
        assert svc.extract_user_identity(payload) == "bob@contoso.com"

    @pytest.mark.asyncio
    async def test_falls_back_to_unique_name(self):
        svc = self._make_svc()
        payload = {"unique_name": "carol@contoso.com"}
        assert svc.extract_user_identity(payload) == "carol@contoso.com"

    @pytest.mark.asyncio
    async def test_falls_back_to_email(self):
        svc = self._make_svc()
        payload = {"email": "dave@contoso.com"}
        assert svc.extract_user_identity(payload) == "dave@contoso.com"

    @pytest.mark.asyncio
    async def test_prefers_upn_over_email(self):
        svc = self._make_svc()
        payload = {"upn": "primary@contoso.com", "email": "alt@contoso.com"}
        assert svc.extract_user_identity(payload) == "primary@contoso.com"

    @pytest.mark.asyncio
    async def test_no_identity_claim_raises(self):
        svc = self._make_svc()
        payload = {"sub": "no-email-here", "oid": "some-guid"}

        with pytest.raises(AuthenticationException, match="identity claim"):
            svc.extract_user_identity(payload)
