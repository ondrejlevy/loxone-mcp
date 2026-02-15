"""Loxone multi-tier authentication.

Implements 3-tier authentication fallback:
1. Token-based via WebSocket (firmware 9.x+) - JWT tokens
2. Token-based via HTTP (firmware 9.x+) - JWT tokens with HTTP RSA key
3. Hash-based HMAC-SHA1 (firmware 8.x legacy)

Protocol flow (token-based):
1. ``getPublicKey`` → RSA-2048 PEM
2. Generate AES-256 key + IV, RSA-encrypt, ``keyexchange/{b64}``
3. ``getkey2/{user}`` → key (hex), salt (hex), hashAlg
4. ``pwd_hash = HASH("password:salt").upper()``
5. ``final_hash = HMAC(key_bytes, "user:pwd_hash")``
6. AES-encrypt: ``salt/{enc_salt}/jdev/sys/getjwt/{hash}/{user}/...\\0``
7. Send: ``jdev/sys/enc/{url_encoded_b64_cipher}``
8. Fallback: ``gettoken`` if ``getjwt`` fails, then hash-based HMAC-SHA1

Includes RSA-2048 key exchange and AES-256-CBC encryption (T016),
and automatic token refresh (T016a).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

if TYPE_CHECKING:
    from loxone_mcp.config import LoxoneConfig

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helper functions (module-level, used by both class methods and standalone)
# ---------------------------------------------------------------------------


def _parse_response(data: str) -> dict[str, Any]:
    """Parse a Loxone JSON response, extracting the LL wrapper."""
    try:
        parsed = json.loads(data)
        result: dict[str, Any] = parsed.get("LL", parsed)
        return result
    except (json.JSONDecodeError, AttributeError):
        return {}


def _is_success(resp: dict[str, Any]) -> bool:
    """Check if a Loxone response indicates success."""
    code = str(resp.get("Code", resp.get("code", "")))
    return code.startswith("2")


async def _recv_text(ws: Any) -> str:
    """Receive a Loxone text response, consuming the binary header first.

    The Miniserver sends every response as two WebSocket frames:
    1. A binary 8-byte header (start=0x03, msg_type, info, payload length)
    2. A text frame with the actual JSON payload

    This helper transparently consumes the binary header and returns only
    the text payload that callers can pass to ``_parse_response``.
    """
    msg = await ws.recv()
    # If first frame is the 8-byte binary header, read the next (text) frame
    if isinstance(msg, bytes):
        msg = await ws.recv()
    return msg if isinstance(msg, str) else msg.decode("utf-8", errors="replace")


def _normalize_public_key(raw_key: str) -> str:
    """Convert Loxone public key/certificate PEM to importable format.

    Loxone may return the key wrapped as ``BEGIN CERTIFICATE`` instead of
    ``BEGIN PUBLIC KEY``.  The ``cryptography`` library only accepts the
    latter, so we rewrite the header/footer when necessary.
    """
    pem = raw_key.strip()
    pem = pem.replace(
        "-----BEGIN CERTIFICATE-----",
        "-----BEGIN PUBLIC KEY-----\n",
    ).replace(
        "-----END CERTIFICATE-----",
        "\n-----END PUBLIC KEY-----\n",
    )
    if not pem.startswith("-----BEGIN"):
        pem = f"-----BEGIN PUBLIC KEY-----\n{pem}\n-----END PUBLIC KEY-----"
    return pem


def _encrypt_ws_command(
    cmd: str,
    aes_key: bytes,
    aes_iv: bytes,
    salt: str,
) -> str:
    """Encrypt a WebSocket command for the Loxone Miniserver.

    The Loxone protocol requires:
    1. ``salt/{hex_salt}/{command}\\x00`` — null-terminated, salt-prefixed
    2. PKCS#7 padded to AES block size
    3. AES-256-CBC encrypted
    4. Base64 encoded
    5. **URL-encoded** — critical because base64 contains ``/`` and ``+``
       that are otherwise interpreted as path separators.

    Returns the URL-encoded base64 cipher ready for ``jdev/sys/enc/{cipher}``.
    """
    plaintext = f"salt/{salt}/{cmd}\x00"
    data = plaintext.encode("utf-8")
    # PKCS7 padding
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    b64 = base64.b64encode(encrypted).decode("ascii")
    return urllib.parse.quote(b64)


async def _fetch_public_key_http(
    host: str,
    port: int,
    username: str,
    password: str,
) -> str:
    """Fetch RSA public key via HTTP (required on modern firmware)."""
    import urllib.request

    url = f"http://{host}:{port}/jdev/sys/getPublicKey"
    req = urllib.request.Request(url)  # noqa: S310
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {credentials}")

    with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
        data = json.loads(response.read())

    resp = data.get("LL", data)
    if not _is_success(resp):
        msg = "Failed to get RSA public key via HTTP"
        raise AuthenticationError(msg)

    return str(resp.get("value", "")).strip()


async def _token_auth(
    ws: Any,
    username: str,
    password: str,
    *,
    public_key_pem: str | None = None,
) -> bool:
    """Attempt token-based authentication (firmware >= 9.x).

    Flow:
    1. Get RSA public key (from *public_key_pem* or via WebSocket)
    2. Generate AES session key + IV, encrypt with RSA, send key exchange
    3. Get key2 (salt + hash algorithm)
    4. Compute HMAC credentials
    5. Request JWT / token (encrypted)

    Returns True on success, raises AuthenticationError on failure.
    """
    # Step 1: Obtain RSA public key
    if public_key_pem is None:
        await ws.send("jdev/sys/getPublicKey")
        resp = _parse_response(await _recv_text(ws))
        if not _is_success(resp):
            raise AuthenticationError("Failed to get RSA public key")
        public_key_pem = str(resp.get("value", "")).strip()

    pub_key_pem = _normalize_public_key(public_key_pem)

    public_key = serialization.load_pem_public_key(pub_key_pem.encode())

    # Step 2: Generate AES-256 session key + IV
    aes_key = secrets.token_bytes(32)  # 256-bit
    aes_iv = secrets.token_bytes(16)  # 128-bit
    # Loxone expects hex-encoded key:iv
    session_key_payload = f"{aes_key.hex()}:{aes_iv.hex()}".encode()

    # Encrypt session key with RSA
    encrypted_session = public_key.encrypt(  # type: ignore[union-attr]
        session_key_payload,
        padding.PKCS1v15(),
    )
    b64_session = base64.b64encode(encrypted_session).decode("ascii")

    await ws.send(f"jdev/sys/keyexchange/{b64_session}")
    resp = _parse_response(await _recv_text(ws))
    if not _is_success(resp):
        raise AuthenticationError("Key exchange failed")

    # Step 3: Get key2 for the user
    await ws.send(f"jdev/sys/getkey2/{username}")
    resp = _parse_response(await _recv_text(ws))
    if not _is_success(resp):
        raise AuthenticationError(f"Failed to get key for user {username!r}")

    key_data = resp.get("value", {})
    key_hex = str(key_data.get("key", ""))
    user_salt = str(key_data.get("salt", ""))
    hash_alg = str(key_data.get("hashAlg", "SHA256")).upper()

    key_bytes = bytes.fromhex(key_hex)

    # Step 4: Compute HMAC credentials (per Loxone protocol / PyLoxone)
    if hash_alg == "SHA1":
        hash_func = hashlib.sha1  # noqa: S324
    else:  # SHA256 or unknown -> default to SHA256
        hash_func = hashlib.sha256

    # pwd_hash = HASH("password:user_salt") -> uppercase hex
    pwd_hash = hash_func(
        f"{password}:{user_salt}".encode()
    ).hexdigest().upper()
    # final_hash = HMAC(key, "username:pwd_hash")
    final_hash = hmac.new(
        key_bytes, f"{username}:{pwd_hash}".encode(), hash_func,
    ).hexdigest()

    # Step 5: Request JWT (firmware >= 10.2) or token
    client_uuid = "edfc5f9a-df3f-4cad-9dffac30c150c33e"
    client_name = "loxone-mcp"
    permission = 2  # web access (short-lived)

    # Random encryption salt (16 bytes = 32 hex chars, per PyLoxone)
    enc_salt = secrets.token_bytes(16).hex()

    # Use getjwt for modern firmware, gettoken as fallback
    token_cmd = (
        f"jdev/sys/getjwt/{final_hash}"
        f"/{username}/{permission}/{client_uuid}/{client_name}"
    )

    enc_cmd = _encrypt_ws_command(token_cmd, aes_key, aes_iv, enc_salt)
    await ws.send(f"jdev/sys/enc/{enc_cmd}")
    resp = _parse_response(await _recv_text(ws))

    if not _is_success(resp):
        # Try gettoken for older firmware
        logger.debug(
            "auth_getjwt_failed_trying_gettoken",
            code=resp.get("Code", resp.get("code")),
        )
        token_cmd_legacy = (
            f"jdev/sys/gettoken/{final_hash}"
            f"/{username}/{permission}/{client_uuid}/{client_name}"
        )
        enc_cmd2 = _encrypt_ws_command(token_cmd_legacy, aes_key, aes_iv, enc_salt)
        await ws.send(f"jdev/sys/enc/{enc_cmd2}")
        resp = _parse_response(await _recv_text(ws))
        if not _is_success(resp):
            raise AuthenticationError("Token authentication failed")

    token_value = resp.get("value", {})
    if isinstance(token_value, dict):
        logger.info(
            "auth_token_acquired",
            valid_until=token_value.get("validUntil"),
        )
    else:
        logger.info("auth_token_acquired")

    return True


async def _hash_auth(
    ws: Any,
    username: str,
    password: str,
) -> bool:
    """Hash-based authentication fallback (firmware 8.x).

    Flow:
    1. Request one-time key
    2. Compute HMAC-SHA1(user:password, key)
    3. Send authenticate/{hash}

    Returns True on success, raises AuthenticationError on failure.
    """
    await ws.send("jdev/sys/getkey")
    resp = _parse_response(await _recv_text(ws))
    if not _is_success(resp):
        raise AuthenticationError("Failed to get authentication key")

    key_hex = str(resp.get("value", ""))
    key_bytes = bytes.fromhex(key_hex)

    # HMAC-SHA1 of "user:password"
    hash_val = hmac.new(
        key_bytes,
        f"{username}:{password}".encode(),
        hashlib.sha1,  # noqa: S324
    ).hexdigest()

    await ws.send(f"authenticate/{hash_val}")
    resp = _parse_response(await _recv_text(ws))
    if not _is_success(resp):
        raise AuthenticationError("Hash-based authentication failed")

    logger.info("auth_hash_based_success")
    return True


class AuthenticationError(Exception):
    """Raised when authentication with the Miniserver fails."""


# ---------------------------------------------------------------------------
# Data classes (backward-compatible)
# ---------------------------------------------------------------------------


class AuthTier(StrEnum):
    """Authentication tier."""

    TOKEN_WS = "token-websocket"
    TOKEN_HTTP = "token-http"
    HASH = "hash-legacy"


@dataclass
class AuthToken:
    """Authenticated session token."""

    token: str
    valid_until: float  # Epoch timestamp
    tier: AuthTier
    token_rights: int = 2
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return time.time() >= self.valid_until

    @property
    def should_refresh(self) -> bool:
        """Check if token should be refreshed (5 min before expiry)."""
        return time.time() >= (self.valid_until - 300)


@dataclass
class AuthSession:
    """Authentication session with key material."""

    public_key_pem: str = ""
    salt: str = ""
    session_key: bytes = field(default_factory=lambda: os.urandom(32))
    session_iv: bytes = field(default_factory=lambda: os.urandom(16))
    token: AuthToken | None = None


# ---------------------------------------------------------------------------
# LoxoneAuthenticator class
# ---------------------------------------------------------------------------


class LoxoneAuthenticator:
    """Multi-tier Loxone authentication handler.

    Attempts authentication in order:
    1. Token-based (WebSocket) - preferred
    2. Token-based (HTTP) - fallback
    3. Hash-based HMAC-SHA1 - legacy fallback
    """

    def __init__(self, config: LoxoneConfig) -> None:
        self._config = config
        self._session = AuthSession()
        self._current_tier: AuthTier | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return (
            self._session.token is not None
            and not self._session.token.is_expired
        )

    @property
    def current_tier(self) -> AuthTier | None:
        """Get the current authentication tier."""
        return self._current_tier

    @property
    def token(self) -> AuthToken | None:
        """Get the current auth token."""
        return self._session.token

    # --- RSA Key Exchange (T016) ---

    def encrypt_with_rsa(self, data: str, public_key_pem: str) -> str:
        """Encrypt data with RSA-2048 public key.

        Args:
            data: Plaintext to encrypt
            public_key_pem: PEM-encoded RSA public key from Loxone

        Returns:
            Base64-encoded encrypted data
        """
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        encrypted = public_key.encrypt(  # type: ignore[union-attr]
            data.encode(),
            padding.PKCS1v15(),
        )
        return base64.b64encode(encrypted).decode()

    def encrypt_with_aes(self, data: str) -> str:
        """Encrypt data with AES-256-CBC using session key.

        Args:
            data: Plaintext to encrypt

        Returns:
            Base64-encoded encrypted data
        """
        # Pad to AES block size (16 bytes)
        pad_len = 16 - (len(data.encode()) % 16)
        padded = data.encode() + bytes([pad_len] * pad_len)

        cipher = Cipher(
            algorithms.AES(self._session.session_key),
            modes.CBC(self._session.session_iv),
        )
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(encrypted).decode()

    def decrypt_with_aes(self, data: str) -> str:
        """Decrypt AES-256-CBC encrypted data.

        Args:
            data: Base64-encoded encrypted data

        Returns:
            Decrypted plaintext
        """
        encrypted = base64.b64decode(data)
        cipher = Cipher(
            algorithms.AES(self._session.session_key),
            modes.CBC(self._session.session_iv),
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()

        # Remove PKCS7 padding
        pad_len = decrypted[-1]
        return decrypted[:-pad_len].decode()

    # --- Hash-based Authentication (Tier 3) ---

    @staticmethod
    def compute_hmac_sha1(password: str, salt: str) -> str:
        """Compute HMAC-SHA1 hash for legacy authentication.

        Args:
            password: Loxone password
            salt: Salt from Loxone getsalt response

        Returns:
            Hex-encoded HMAC-SHA1 hash
        """
        key = password.encode("utf-8")
        message = f"{salt}".encode()
        return hmac.new(key, message, hashlib.sha1).hexdigest()

    @staticmethod
    def compute_hash_credentials(
        username: str, password: str, salt: str, hash_alg: str = "SHA1"
    ) -> str:
        """Compute hashed credentials for legacy auth.

        Args:
            username: Loxone username
            password: Loxone password
            salt: Salt from Loxone
            hash_alg: Hash algorithm (SHA1 or SHA256)

        Returns:
            Hashed credential string
        """
        if hash_alg.upper() == "SHA256":
            pw_hash = hashlib.sha256(f"{password}:{salt}".encode()).hexdigest()
        else:
            pw_hash = hashlib.sha1(  # noqa: S324
                f"{password}:{salt}".encode()
            ).hexdigest()

        # HMAC of user:pwHash
        hmac_hash = hmac.new(
            pw_hash.encode(),
            username.encode(),
            hashlib.sha1 if hash_alg.upper() == "SHA1" else hashlib.sha256,
        ).hexdigest()

        return hmac_hash

    # --- Token Authentication Commands ---

    def build_key_exchange_command(self) -> str:
        """Build the session key exchange command.

        Sends our AES session key + IV encrypted with Loxone's RSA public key.
        """
        session_key_hex = self._session.session_key.hex()
        session_iv_hex = self._session.session_iv.hex()
        payload = f"{session_key_hex}:{session_iv_hex}"

        if self._session.public_key_pem:
            encrypted = self.encrypt_with_rsa(payload, self._session.public_key_pem)
            return f"jdev/sys/keyexchange/{encrypted}"
        msg = "No public key available for key exchange"
        raise RuntimeError(msg)

    def build_token_command(self) -> str:
        """Build the gettoken command with encrypted credentials."""
        creds = f"{self._config.username}:{self._config.password}"
        encrypted = self.encrypt_with_aes(creds)
        return f"jdev/sys/getjwt/{encrypted}/2/{self._config.username}"

    def build_refresh_command(self) -> str:
        """Build the token refresh command."""
        if self._session.token is None:
            msg = "No token to refresh"
            raise RuntimeError(msg)
        token_hash = hashlib.sha256(self._session.token.token.encode()).hexdigest()
        return f"jdev/sys/refreshjwt/{token_hash}/{self._config.username}"

    def build_hash_auth_command(self, salt: str, hash_alg: str = "SHA1") -> str:
        """Build the hash-based authentication command."""
        cred_hash = self.compute_hash_credentials(
            self._config.username, self._config.password, salt, hash_alg
        )
        return f"authenticate/{cred_hash}"

    # --- Response Processing ---

    def process_getkey_response(self, response: dict[str, Any]) -> None:
        """Process response from jdev/sys/getkey2."""
        value = response.get("LL", {}).get("value", {})
        self._session.public_key_pem = value.get("key", "")
        self._session.salt = value.get("salt", "")
        logger.debug("auth_getkey_received", has_key=bool(self._session.public_key_pem))

    def process_token_response(self, response: dict[str, Any], tier: AuthTier) -> AuthToken:
        """Process response from gettoken/getjwt."""
        value = response.get("LL", {}).get("value", {})
        token = AuthToken(
            token=value.get("token", ""),
            valid_until=float(value.get("validUntil", 0)),
            tier=tier,
            token_rights=int(value.get("tokenRights", 2)),
        )
        self._session.token = token
        self._current_tier = tier
        logger.info(
            "auth_token_acquired",
            tier=tier.value,
            valid_until=token.valid_until,
        )
        return token

    def process_refresh_response(self, response: dict[str, Any]) -> bool:
        """Process response from refreshjwt."""
        code = response.get("LL", {}).get("Code", "")
        if str(code) == "200":
            value = response.get("LL", {}).get("value", {})
            if self._session.token:
                self._session.token.valid_until = float(value.get("validUntil", 0))
                self._session.token.created_at = time.time()
            logger.info("auth_token_refreshed")
            return True
        logger.warning("auth_token_refresh_failed", code=code)
        return False

    # --- WebSocket Authentication (called from websocket.py) ---

    async def authenticate_ws(self, ws: Any) -> bool:
        """Authenticate over an open WebSocket connection.

        Implements a 3-tier fallback:
        1. Token auth with WS-provided RSA public key
        2. Token auth with HTTP-provided RSA public key
        3. Hash-based HMAC-SHA1 legacy auth

        Args:
            ws: An open WebSocket connection (websockets ClientConnection).

        Returns:
            True on successful authentication.
        """
        username = self._config.username
        password = self._config.password

        # --- Attempt 1: token auth with WS-provided public key ---
        try:
            result = await _token_auth(ws, username, password)
            self._current_tier = AuthTier.TOKEN_WS
            logger.info("auth_ws_token_success", tier="ws")
            return result
        except AuthenticationError:
            logger.info("auth_token_ws_unavailable")
        except Exception as exc:
            logger.debug("auth_token_ws_error", error=str(exc))

        # --- Attempt 2: token auth with HTTP-provided public key ---
        host = self._config.host
        port = self._config.port
        if host:
            try:
                pk = await _fetch_public_key_http(host, port, username, password)
                logger.info("auth_fetched_rsa_key_via_http")
                result = await _token_auth(
                    ws, username, password, public_key_pem=pk,
                )
                self._current_tier = AuthTier.TOKEN_HTTP
                logger.info("auth_ws_token_success", tier="http")
                return result
            except AuthenticationError:
                logger.info("auth_token_http_also_failed")
            except Exception as exc:
                logger.debug("auth_token_http_error", error=str(exc))

        # --- Attempt 3: legacy hash-based auth ---
        try:
            result = await _hash_auth(ws, username, password)
            self._current_tier = AuthTier.HASH
            logger.info("auth_hash_success")
            return result
        except AuthenticationError as exc:
            raise AuthenticationError(
                "All authentication methods failed"
            ) from exc

    # --- Token Refresh (T016a) ---

    async def start_token_refresh(
        self,
        send_command: Any,  # Callable to send commands via WebSocket/HTTP
    ) -> None:
        """Start automatic token refresh background task.

        Refreshes token 5 minutes before expiry.
        If refresh fails, attempts full re-authentication.
        """
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        self._refresh_task = asyncio.create_task(
            self._refresh_loop(send_command)
        )

    async def _refresh_loop(self, send_command: Any) -> None:
        """Background loop to refresh tokens before expiry."""
        while True:
            try:
                if self._session.token is None:
                    await asyncio.sleep(30)
                    continue

                if self._session.token.should_refresh:
                    logger.info("auth_token_refresh_starting")
                    try:
                        cmd = self.build_refresh_command()
                        response = await send_command(cmd)
                        if not self.process_refresh_response(response):
                            # Refresh failed, try full re-auth
                            logger.warning("auth_refresh_failed_reauthenticating")
                            break  # Exit loop to trigger re-authentication
                    except Exception:
                        logger.exception("auth_refresh_error")
                        break

                # Check every 30 seconds
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.debug("auth_refresh_task_cancelled")
                return

    def stop_token_refresh(self) -> None:
        """Stop the token refresh background task."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            self._refresh_task = None

    def reset(self) -> None:
        """Reset authentication state."""
        self.stop_token_refresh()
        self._session = AuthSession()
        self._current_tier = None
        logger.info("auth_session_reset")
