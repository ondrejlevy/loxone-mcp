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

    async def fetch_structure_file(self) -> StructureFile:
        """Fetch and parse the Loxone structure file.

        Implements retry logic: 3 attempts with exponential backoff (1s, 2s, 4s).

        Returns:
            Parsed StructureFile

        Raises:
            ConnectionError: If all retries fail
        """
        url = f"{self.base_url}/jdev/sps/LoxAPP3.json"
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
        url = f"{self.base_url}/jdev/sps/LoxAPP3.json"
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

                if str(code) != "200":
                    logger.warning(
                        "loxone_command_error",
                        command=command,
                        code=code,
                        value=data.get("LL", {}).get("value"),
                    )

                duration = time.monotonic() - start
                loxone_api_duration.labels(endpoint="send_command").observe(duration)
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
