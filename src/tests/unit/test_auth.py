"""Unit tests for Loxone authentication (auth.py).

Tests multi-tier authentication, encryption, token management,
and session lifecycle.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from loxone_mcp.loxone.auth import (
    AuthSession,
    AuthTier,
    AuthToken,
    LoxoneAuthenticator,
)

# --- AuthToken Tests ---


class TestAuthToken:
    def test_not_expired(self) -> None:
        token = AuthToken(token="abc", valid_until=time.time() + 3600, tier=AuthTier.TOKEN_WS)
        assert token.is_expired is False

    def test_expired(self) -> None:
        token = AuthToken(token="abc", valid_until=time.time() - 1, tier=AuthTier.TOKEN_WS)
        assert token.is_expired is True

    def test_should_refresh_when_close_to_expiry(self) -> None:
        token = AuthToken(token="abc", valid_until=time.time() + 100, tier=AuthTier.TOKEN_WS)
        assert token.should_refresh is True  # < 300s to expiry

    def test_should_not_refresh_when_far_from_expiry(self) -> None:
        token = AuthToken(token="abc", valid_until=time.time() + 600, tier=AuthTier.TOKEN_WS)
        assert token.should_refresh is False  # > 300s to expiry

    def test_default_token_rights(self) -> None:
        token = AuthToken(token="abc", valid_until=0, tier=AuthTier.HASH)
        assert token.token_rights == 2


class TestAuthTier:
    def test_tier_values(self) -> None:
        assert AuthTier.TOKEN_WS == "token-websocket"
        assert AuthTier.TOKEN_HTTP == "token-http"
        assert AuthTier.HASH == "hash-legacy"


# --- AuthSession Tests ---


class TestAuthSession:
    def test_default_session(self) -> None:
        session = AuthSession()
        assert session.public_key_pem == ""
        assert session.salt == ""
        assert len(session.session_key) == 32
        assert len(session.session_iv) == 16
        assert session.token is None


# --- LoxoneAuthenticator Tests ---


def _make_config() -> Any:
    config = MagicMock()
    config.host = "192.168.1.100"
    config.port = 80
    config.username = "testuser"
    config.password = "testpass"
    config.use_tls = False
    return config


class TestLoxoneAuthenticator:
    def test_initial_state(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        assert auth.is_authenticated is False
        assert auth.current_tier is None
        assert auth.token is None

    def test_is_authenticated_with_valid_token(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.token = AuthToken(
            token="abc", valid_until=time.time() + 3600, tier=AuthTier.TOKEN_WS
        )
        assert auth.is_authenticated is True

    def test_is_authenticated_with_expired_token(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.token = AuthToken(
            token="abc", valid_until=time.time() - 1, tier=AuthTier.TOKEN_WS
        )
        assert auth.is_authenticated is False


class TestEncryption:
    def test_aes_encrypt_decrypt_roundtrip(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        original = "hello world test data"
        encrypted = auth.encrypt_with_aes(original)
        decrypted = auth.decrypt_with_aes(encrypted)
        assert decrypted == original

    def test_aes_different_data_produces_different_cipher(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        enc1 = auth.encrypt_with_aes("data one")
        enc2 = auth.encrypt_with_aes("data two")
        assert enc1 != enc2

    def test_rsa_encrypt(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        auth = LoxoneAuthenticator(_make_config())
        encrypted = auth.encrypt_with_rsa("test data", public_key_pem)
        assert encrypted  # Not empty
        assert encrypted != "test data"


class TestHashing:
    def test_compute_hmac_sha1(self) -> None:
        result = LoxoneAuthenticator.compute_hmac_sha1("password", "salt123")
        expected = hmac.new(b"password", b"salt123", hashlib.sha1).hexdigest()
        assert result == expected

    def test_compute_hash_credentials_sha1(self) -> None:
        result = LoxoneAuthenticator.compute_hash_credentials("user", "pass", "salt", "SHA1")
        assert isinstance(result, str)
        assert len(result) == 40  # SHA1 hex digest length

    def test_compute_hash_credentials_sha256(self) -> None:
        result = LoxoneAuthenticator.compute_hash_credentials("user", "pass", "salt", "SHA256")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex digest length


class TestCommandBuilders:
    def test_build_key_exchange_no_key_raises(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.public_key_pem = ""
        with pytest.raises(RuntimeError, match="No public key"):
            auth.build_key_exchange_command()

    def test_build_key_exchange_with_key(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        auth = LoxoneAuthenticator(_make_config())
        auth._session.public_key_pem = pem
        cmd = auth.build_key_exchange_command()
        assert cmd.startswith("jdev/sys/keyexchange/")

    def test_build_token_command(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        cmd = auth.build_token_command()
        assert "jdev/sys/getjwt/" in cmd
        assert "/testuser" in cmd

    def test_build_refresh_command(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.token = AuthToken(
            token="mytoken", valid_until=time.time() + 3600, tier=AuthTier.TOKEN_WS
        )
        cmd = auth.build_refresh_command()
        assert "jdev/sys/refreshjwt/" in cmd
        assert "/testuser" in cmd

    def test_build_refresh_no_token_raises(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        with pytest.raises(RuntimeError, match="No token"):
            auth.build_refresh_command()

    def test_build_hash_auth_command(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        cmd = auth.build_hash_auth_command("salt123", "SHA1")
        assert cmd.startswith("authenticate/")


class TestResponseProcessing:
    def test_process_getkey_response(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        response = {
            "LL": {
                "value": {"key": "-----BEGIN PUBLIC KEY-----\nABC\n", "salt": "salt123"},
                "Code": "200",
            }
        }
        auth.process_getkey_response(response)
        assert auth._session.public_key_pem == "-----BEGIN PUBLIC KEY-----\nABC\n"
        assert auth._session.salt == "salt123"

    def test_process_token_response(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        response = {
            "LL": {
                "value": {"token": "jwt_token_abc", "validUntil": 9999999999, "tokenRights": 4},
                "Code": "200",
            }
        }
        token = auth.process_token_response(response, AuthTier.TOKEN_WS)
        assert token.token == "jwt_token_abc"
        assert token.valid_until == 9999999999
        assert token.token_rights == 4
        assert auth.current_tier == AuthTier.TOKEN_WS

    def test_process_refresh_response_success(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.token = AuthToken(
            token="old", valid_until=1000, tier=AuthTier.TOKEN_WS
        )
        response = {"LL": {"Code": "200", "value": {"validUntil": 9999999999}}}
        result = auth.process_refresh_response(response)
        assert result is True
        assert auth._session.token.valid_until == 9999999999

    def test_process_refresh_response_failure(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        response = {"LL": {"Code": "401", "value": "expired"}}
        result = auth.process_refresh_response(response)
        assert result is False


class TestTokenRefresh:
    async def test_start_token_refresh(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        send_command = AsyncMock()
        await auth.start_token_refresh(send_command)
        assert auth._refresh_task is not None
        auth.stop_token_refresh()

    async def test_stop_token_refresh(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._refresh_task = asyncio.create_task(asyncio.sleep(1000))
        auth.stop_token_refresh()
        assert auth._refresh_task is None

    async def test_reset(self) -> None:
        auth = LoxoneAuthenticator(_make_config())
        auth._session.token = AuthToken(
            token="abc", valid_until=time.time() + 3600, tier=AuthTier.TOKEN_WS
        )
        auth._current_tier = AuthTier.TOKEN_WS
        auth.reset()
        assert auth.token is None
        assert auth.current_tier is None
