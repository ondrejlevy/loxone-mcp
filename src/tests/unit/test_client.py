"""Unit tests for Loxone HTTP client (client.py).

Tests structure file fetching, command sending, retry logic, and error handling.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loxone_mcp.loxone.client import LoxoneClient


def _make_client() -> LoxoneClient:
    config = MagicMock()
    config.host = "192.168.1.100"
    config.port = 80
    config.username = "testuser"
    config.password = "testpass"
    config.use_tls = False
    authenticator = MagicMock()
    return LoxoneClient(config, authenticator)


def _mock_response(status: int = 200, json_data: Any = None) -> MagicMock:
    """Create a mock aiohttp response as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


def _mock_session(response: MagicMock) -> MagicMock:
    """Create a mock aiohttp session where get() returns an async context manager."""
    session = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=cm)
    session.closed = False
    session.close = AsyncMock()
    return session


class TestBaseUrl:
    def test_http_url(self) -> None:
        client = _make_client()
        assert client.base_url == "http://192.168.1.100:80"

    def test_https_url(self) -> None:
        client = _make_client()
        client._config.use_tls = True
        assert client.base_url == "https://192.168.1.100:80"


class TestFetchStructureFile:
    @patch("loxone_mcp.loxone.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_success(self, mock_sleep: AsyncMock) -> None:
        client = _make_client()
        from tests.fixtures.loxone_responses import load_structure_file

        structure_data = load_structure_file()
        response = _mock_response(200, structure_data)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            structure = await client.fetch_structure_file()
            assert len(structure.controls) > 0
            assert client._structure_hash is not None

    @patch("loxone_mcp.loxone.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_http_error_retries(self, mock_sleep: AsyncMock) -> None:
        client = _make_client()
        response = _mock_response(500, None)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            with pytest.raises(ConnectionError, match="Failed to fetch"):
                await client.fetch_structure_file()

    @patch("loxone_mcp.loxone.client.asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_connection_error_retries(self, mock_sleep: AsyncMock) -> None:
        client = _make_client()
        session = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=OSError("Network down"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=cm)

        with patch.object(client, "_get_session", return_value=session):
            with pytest.raises(ConnectionError, match="Failed to fetch"):
                await client.fetch_structure_file()


class TestCheckStructureChanged:
    async def test_no_change(self) -> None:
        client = _make_client()
        data = {"foo": "bar"}
        raw_text = json.dumps(data, sort_keys=True)
        client._structure_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        response = _mock_response(200, data)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            changed = await client.check_structure_changed()
            assert changed is False

    async def test_change_detected(self) -> None:
        client = _make_client()
        client._structure_hash = "old_hash"

        response = _mock_response(200, {"new": "data"})
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            changed = await client.check_structure_changed()
            assert changed is True

    async def test_http_error_returns_false(self) -> None:
        client = _make_client()
        response = _mock_response(500, None)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            changed = await client.check_structure_changed()
            assert changed is False

    async def test_exception_returns_false(self) -> None:
        client = _make_client()
        session = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=Exception("error"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=cm)

        with patch.object(client, "_get_session", return_value=session):
            changed = await client.check_structure_changed()
            assert changed is False


class TestSendCommand:
    @patch("loxone_mcp.metrics.collector.loxone_api_duration")
    async def test_success(self, mock_metric: MagicMock) -> None:
        client = _make_client()
        response_data = {"LL": {"Code": "200", "value": "OK"}}
        response = _mock_response(200, response_data)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            result = await client.send_command("jdev/sps/io/uuid/On")
            assert result["LL"]["Code"] == "200"

    @patch("loxone_mcp.metrics.collector.loxone_api_duration")
    async def test_non_200_code_still_returns(self, mock_metric: MagicMock) -> None:
        client = _make_client()
        response_data = {"LL": {"Code": "500", "value": "Error"}}
        response = _mock_response(200, response_data)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            result = await client.send_command("test")
            assert result["LL"]["Code"] == "500"

    @patch("loxone_mcp.metrics.collector.loxone_api_duration")
    async def test_timeout_error(self, mock_metric: MagicMock) -> None:
        client = _make_client()
        session = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=TimeoutError("timeout"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session.get = MagicMock(return_value=cm)

        with patch.object(client, "_get_session", return_value=session):
            with pytest.raises(TimeoutError):
                await client.send_command("test")


class TestControlComponent:
    @patch("loxone_mcp.metrics.collector.loxone_api_duration")
    async def test_control_component(self, mock_metric: MagicMock) -> None:
        client = _make_client()
        response_data = {"LL": {"Code": "200", "value": "OK"}}
        response = _mock_response(200, response_data)
        session = _mock_session(response)

        with patch.object(client, "_get_session", return_value=session):
            result = await client.control_component("uuid-123", "On")
            assert result["LL"]["Code"] == "200"


class TestClose:
    async def test_close_session(self) -> None:
        client = _make_client()
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock()
        client._session = session
        await client.close()
        session.close.assert_awaited_once()
        assert client._session is None

    async def test_close_no_session(self) -> None:
        client = _make_client()
        client._session = None
        await client.close()  # Should not raise

    async def test_close_already_closed(self) -> None:
        client = _make_client()
        session = MagicMock()
        session.closed = True
        client._session = session
        await client.close()  # Should not close again


class TestGetSession:
    async def test_creates_session(self) -> None:
        client = _make_client()
        client._session = None
        with patch("loxone_mcp.loxone.client.aiohttp.ClientSession") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.closed = False
            mock_cls.return_value = mock_instance

            session = await client._get_session()
            assert session is mock_instance

    async def test_reuses_session(self) -> None:
        client = _make_client()
        mock_session = MagicMock()
        mock_session.closed = False
        client._session = mock_session

        session = await client._get_session()
        assert session is mock_session

    async def test_recreates_closed_session(self) -> None:
        client = _make_client()
        old_session = MagicMock()
        old_session.closed = True
        client._session = old_session

        with patch("loxone_mcp.loxone.client.aiohttp.ClientSession") as mock_cls:
            new_session = MagicMock()
            new_session.closed = False
            mock_cls.return_value = new_session

            session = await client._get_session()
            assert session is new_session
