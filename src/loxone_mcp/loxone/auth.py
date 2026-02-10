"""Loxone multi-tier authentication.

Implements 3-tier authentication fallback:
1. Token-based via WebSocket (firmware 9.x+) - JWT tokens
2. Token-based via HTTP (firmware 9.x+) - JWT tokens
3. Hash-based HMAC-SHA1 (firmware 8.x legacy)

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
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from loxone_mcp.config import LoxoneConfig

logger = structlog.get_logger()


class AuthTier(str, Enum):
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
        message = f"{salt}".encode("utf-8")
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
