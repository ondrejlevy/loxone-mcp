"""Loxone HTTP and WebSocket API client.

Handles structure file retrieval and control command execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Any

import aiohttp
import structlog

from loxone_mcp.loxone.structure import parse_structure_file

if TYPE_CHECKING:
    from loxone_mcp.config import LoxoneConfig
    from loxone_mcp.loxone.auth import LoxoneAuthenticator
    from loxone_mcp.loxone.models import StructureFile

logger = structlog.get_logger()


class LoxoneCommandError(Exception):
    """Loxone miniserver returned a non-200 response code for a command."""

    def __init__(self, command: str, code: str, value: Any = None) -> None:
        self.command = command
        self.code = code
        self.value = value
        super().__init__(f"Loxone command failed: {command} (code={code}, value={value})")


# Retry config
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff
COMMAND_TIMEOUT = 30.0


class LoxoneClient:
    """High-level client for Loxone miniserver API.

    Manages HTTP session and provides methods for structure file
    retrieval and control command execution.
    """

    def __init__(
        self,
        config: LoxoneConfig,
        authenticator: LoxoneAuthenticator,
    ) -> None:
        self._config = config
        self._auth = authenticator
        self._session: aiohttp.ClientSession | None = None
        self._structure_hash: str | None = None
        self._detected_endpoint: str | None = None  # Cache detected endpoint

    @property
    def base_url(self) -> str:
        """Get the base URL for the Loxone miniserver."""
        scheme = "https" if self._config.use_tls else "http"
        return f"{scheme}://{self._config.host}:{self._config.port}"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            auth = aiohttp.BasicAuth(self._config.username, self._config.password)
            timeout = aiohttp.ClientTimeout(total=COMMAND_TIMEOUT)
            self._session = aiohttp.ClientSession(
                auth=auth,
                timeout=timeout,
            )
        return self._session

    async def _detect_structure_endpoint(self) -> str:
        """Detect the correct structure file endpoint.

        Tries multiple endpoints in order:
        1. /jdev/sps/LoxAPP3.json (newer firmware)
        2. /data/LoxAPP3.json (older firmware)

        Returns:
            The working endpoint path

        Raises:
            ConnectionError: If no endpoint works
        """
        endpoints = [
            "/jdev/sps/LoxAPP3.json",
            "/data/LoxAPP3.json",
        ]

        session = await self._get_session()
        for endpoint in endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info(
                            "structure_endpoint_detected",
                            endpoint=endpoint,
                        )
                        return endpoint
            except Exception as e:
                logger.debug(
                    "structure_endpoint_test_failed",
                    endpoint=endpoint,
                    error=str(e),
                )
                continue

        msg = f"No working structure endpoint found. Tried: {', '.join(endpoints)}"
        raise ConnectionError(msg)

    async def fetch_structure_file(self) -> StructureFile:
        """Fetch and parse the Loxone structure file.

        Implements retry logic: 3 attempts with exponential backoff (1s, 2s, 4s).
        Supports configurable endpoint with auto-detection fallback.

        Returns:
            Parsed StructureFile

        Raises:
            ConnectionError: If all retries fail
        """
        # Determine endpoint to use
        if self._detected_endpoint:
            # Use previously detected endpoint
            endpoint = self._detected_endpoint
        elif self._config.structure_endpoint == "auto":
            # Auto-detect endpoint on first call
            endpoint = await self._detect_structure_endpoint()
            self._detected_endpoint = endpoint
        else:
            # Use configured endpoint
            endpoint = self._config.structure_endpoint

        url = f"{self.base_url}{endpoint}"
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.get(url) as response:
                    if response.status != 200:
                        msg = f"Structure file fetch failed: HTTP {response.status}"
                        raise aiohttp.ClientError(msg)

                    data = await response.json(content_type=None)

                    # Compute hash for change detection
                    raw_text = json.dumps(data, sort_keys=True)
                    new_hash = hashlib.sha256(raw_text.encode()).hexdigest()
                    self._structure_hash = new_hash

                    structure = parse_structure_file(data)
                    logger.info(
                        "structure_file_fetched",
                        components=len(structure.controls),
                        attempt=attempt + 1,
                    )

                    # Metrics (T055)

                    # Record the successful fetch (duration tracked at higher level)
                    return structure

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "structure_file_fetch_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        msg = f"Failed to fetch structure file after {MAX_RETRIES} attempts"
        raise ConnectionError(msg) from last_error

    async def check_structure_changed(self) -> bool:
        """Check if structure file has changed by comparing hashes.

        Used for periodic change detection (T035a).

        Returns:
            True if structure has changed, False otherwise
        """
        # Use the detected or configured endpoint
        if self._detected_endpoint:
            endpoint = self._detected_endpoint
        elif self._config.structure_endpoint != "auto":
            endpoint = self._config.structure_endpoint
        else:
            # Fall back to standard endpoint if not yet detected
            endpoint = "/jdev/sps/LoxAPP3.json"

        url = f"{self.base_url}{endpoint}"
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    return False

                data = await response.json(content_type=None)
                raw_text = json.dumps(data, sort_keys=True)
                new_hash = hashlib.sha256(raw_text.encode()).hexdigest()

                if self._structure_hash and new_hash != self._structure_hash:
                    logger.info("structure_change_detected")
                    self._structure_hash = new_hash
                    return True
                return False

        except Exception:
            logger.exception("structure_change_check_error")
            return False

    async def send_command(
        self,
        command: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a command to the Loxone miniserver via HTTP.

        Args:
            command: Loxone API command path (e.g., "jdev/sps/io/{uuid}/{action}")
            params: Optional parameters

        Returns:
            Response data

        Raises:
            TimeoutError: If command times out after 30s
            ConnectionError: If miniserver is unreachable
        """
        url = f"{self.base_url}/{command}"
        session = await self._get_session()

        # Metrics instrumentation (T055)
        import time

        from loxone_mcp.metrics.collector import loxone_api_duration

        start = time.monotonic()
        try:
            async with session.get(url) as response:
                data = await response.json(content_type=None)
                code = data.get("LL", {}).get("Code", "")

                duration = time.monotonic() - start
                loxone_api_duration.labels(endpoint="send_command").observe(duration)

                if str(code) != "200":
                    value = data.get("LL", {}).get("value")
                    logger.warning(
                        "loxone_command_error",
                        command=command,
                        code=code,
                        value=value,
                    )
                    raise LoxoneCommandError(command, str(code), value)

                result: dict[str, Any] = data
                return result

        except TimeoutError:
            logger.error("loxone_command_timeout", command=command)
            raise
        except aiohttp.ClientError as e:
            logger.error("loxone_command_error", command=command, error=str(e))
            raise ConnectionError(str(e)) from e

    async def control_component(
        self,
        uuid: str,
        action: str,
    ) -> dict[str, Any]:
        """Send a control command to a specific component.

        Args:
            uuid: Component UUID
            action: Action to perform (e.g., "On", "Off", "Dim/75")

        Returns:
            Command response data
        """
        command = f"jdev/sps/io/{uuid}/{action}"
        return await self.send_command(command)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def fetch_state_value(self, state_uuid: str) -> Any:
        """Fetch a single state value from the miniserver via HTTP.

        Args:
            state_uuid: The state UUID (Loxone format) to query

        Returns:
            The state value (float or str), or None if not available
        """
        url = f"{self.base_url}/jdev/sps/io/{state_uuid}"
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    logger.debug(
                        "fetch_state_http_error",
                        uuid=state_uuid,
                        status=response.status,
                    )
                    return None
                data = await response.json(content_type=None)
                code = str(data.get("LL", {}).get("Code", data.get("LL", {}).get("code", "")))
                if code != "200":
                    logger.debug(
                        "fetch_state_loxone_error",
                        uuid=state_uuid,
                        code=code,
                    )
                    return None
                value = data.get("LL", {}).get("value")
                if value is None:
                    return None
                # Try to convert to number
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return value
        except Exception:
            logger.debug("fetch_state_value_failed", state_uuid=state_uuid)
            return None

    async def fetch_component_states(
        self,
        states: dict[str, str],
    ) -> dict[str, Any]:
        """Fetch all state values for a component via HTTP.

        Uses parallel requests with a concurrency limit for efficiency.

        Args:
            states: Mapping of state_key -> state_uuid (from Component.states)

        Returns:
            Dict of state_key -> value for successfully fetched states
        """
        import asyncio as _aio

        semaphore = _aio.Semaphore(5)  # Max 5 concurrent requests

        async def _fetch_one(state_key: str, state_uuid: str) -> tuple[str, Any]:
            async with semaphore:
                value = await self.fetch_state_value(state_uuid)
                return state_key, value

        tasks = [
            _fetch_one(key, uuid_path)
            for key, uuid_path in states.items()
        ]
        results = await _aio.gather(*tasks)
        return {key: value for key, value in results if value is not None}
