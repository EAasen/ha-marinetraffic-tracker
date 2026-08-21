"""Tests for BarentsWatch OAuth2 authentication in KystverketClient."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.marinetraffic_tracker.kystverket_client import (
    _TOKEN_REFRESH_BUFFER,
    KystverketClient,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLIENT_ID = "test-client-id"
_CLIENT_SECRET = "test-client-secret"


def _make_client(session: MagicMock | None = None) -> KystverketClient:
    """Return a KystverketClient with the given session (or a fresh mock)."""
    if session is None:
        session = MagicMock()
    return KystverketClient(session, _CLIENT_ID, _CLIENT_SECRET)


def _mock_token_response(
    access_token: str = "test-token",
    expires_in: int = 3600,
    status: int = 200,
) -> MagicMock:
    """Build a mock aiohttp response that returns an OAuth2 token payload."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value={"access_token": access_token, "expires_in": expires_in})
    resp.raise_for_status = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_error_response(status: int) -> MagicMock:
    """Build a mock aiohttp response that returns an error status."""
    resp = MagicMock()
    resp.status = status
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Successful token acquisition
# ---------------------------------------------------------------------------


async def test_get_access_token_returns_token_on_success() -> None:
    """A 200 response with a valid payload should return the access token."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response(access_token="my-token"))

    client = _make_client(session)
    token = await client._get_access_token()

    assert token == "my-token"


async def test_get_access_token_stores_token_and_expiry() -> None:
    """After a successful fetch the token and expiry should be cached internally."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response(expires_in=1800))

    client = _make_client(session)
    await client._get_access_token()

    assert client._access_token == "test-token"
    assert client._token_expiry is not None
    # Expiry should be roughly (1800 - _TOKEN_REFRESH_BUFFER) seconds in the future.
    expected_seconds = 1800 - _TOKEN_REFRESH_BUFFER
    delta = client._token_expiry - datetime.now(UTC)
    assert abs(delta.total_seconds() - expected_seconds) < 5


async def test_get_access_token_sends_correct_credentials() -> None:
    """The token request must include client_id, client_secret, scope, and grant_type."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response())

    client = _make_client(session)
    await client._get_access_token()

    call_kwargs = session.post.call_args
    posted_data = call_kwargs.kwargs.get("data") or call_kwargs.kwargs.get("data")
    # Fall back to positional arg if the call used positional arguments.
    if posted_data is None and len(call_kwargs.args) > 1:
        posted_data = call_kwargs.args[1]
    assert posted_data is not None, "Expected 'data' to be passed to session.post"
    assert posted_data["client_id"] == _CLIENT_ID
    assert posted_data["client_secret"] == _CLIENT_SECRET
    assert posted_data["scope"] == "ais"
    assert posted_data["grant_type"] == "client_credentials"


# ---------------------------------------------------------------------------
# Token caching — valid (non-expired) token reuse
# ---------------------------------------------------------------------------


async def test_cached_token_is_reused_when_not_expired() -> None:
    """A still-valid cached token must be returned without making a new HTTP request."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response())

    client = _make_client(session)
    # Pre-populate the cache with a token that expires far in the future.
    client._access_token = "cached-token"
    client._token_expiry = datetime.now(UTC) + timedelta(hours=1)

    token = await client._get_access_token()

    assert token == "cached-token"
    session.post.assert_not_called()


async def test_expired_token_triggers_refresh() -> None:
    """An expired cached token must be replaced by fetching a new one."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response(access_token="fresh-token"))

    client = _make_client(session)
    # Simulate an already-expired token.
    client._access_token = "stale-token"
    client._token_expiry = datetime.now(UTC) - timedelta(seconds=1)

    token = await client._get_access_token()

    assert token == "fresh-token"
    session.post.assert_called_once()


async def test_none_token_triggers_fetch() -> None:
    """A None cached token must always result in a fresh fetch."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response(access_token="brand-new-token"))

    client = _make_client(session)
    assert client._access_token is None

    token = await client._get_access_token()

    assert token == "brand-new-token"
    session.post.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling — HTTP 400 (bad request / wrong credentials)
# ---------------------------------------------------------------------------


async def test_http_400_raises_runtime_error_mentioning_credentials() -> None:
    """A 400 response must raise RuntimeError with guidance to check credentials."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_error_response(status=400))

    client = _make_client(session)

    with pytest.raises(RuntimeError, match="400") as exc_info:
        await client._get_access_token()
    assert "Client ID" in str(exc_info.value) or "Client Secret" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Error handling — HTTP 401 (invalid credentials)
# ---------------------------------------------------------------------------


async def test_http_401_raises_runtime_error_mentioning_invalid_credentials() -> None:
    """A 401 response must raise RuntimeError indicating the credentials are invalid."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_error_response(status=401))

    client = _make_client(session)

    with pytest.raises(RuntimeError, match="401") as exc_info:
        await client._get_access_token()
    assert "invalid" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Token expiry buffer
# ---------------------------------------------------------------------------


async def test_token_expiry_respects_refresh_buffer() -> None:
    """The cached expiry must be reduced by _TOKEN_REFRESH_BUFFER seconds."""
    session = MagicMock()
    expires_in = 3600
    session.post = MagicMock(return_value=_mock_token_response(expires_in=expires_in))

    client = _make_client(session)
    before = datetime.now(UTC)
    await client._get_access_token()
    after = datetime.now(UTC)

    expected_min = before + timedelta(seconds=expires_in - _TOKEN_REFRESH_BUFFER - 1)
    expected_max = after + timedelta(seconds=expires_in - _TOKEN_REFRESH_BUFFER + 1)
    assert expected_min <= client._token_expiry <= expected_max


async def test_zero_expires_in_results_in_immediate_expiry() -> None:
    """When expires_in is 0 the expiry should be set to 'now' (max with 0 buffer)."""
    session = MagicMock()
    session.post = MagicMock(return_value=_mock_token_response(expires_in=0))

    client = _make_client(session)
    before = datetime.now(UTC)
    await client._get_access_token()

    # Token should already be expired or expire very soon.
    assert client._token_expiry <= before + timedelta(seconds=2)
