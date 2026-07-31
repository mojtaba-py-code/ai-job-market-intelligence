"""Tests for password hashing and JWT tokens."""

from __future__ import annotations

from datetime import timedelta

import pytest

from jmi.infrastructure.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cure-p@ss")
    assert hashed != "s3cure-p@ss"
    assert verify_password("s3cure-p@ss", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_hash_is_salted():
    assert hash_password("same") != hash_password("same")


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")
    assert verify_password("", "whatever") is False


def test_verify_handles_malformed_hash():
    assert verify_password("pw", "not-a-bcrypt-hash") is False


def test_token_roundtrip_carries_claims():
    token = create_access_token("42", role="admin")
    claims = decode_access_token(token)
    assert claims["sub"] == "42"
    assert claims["role"] == "admin"


def test_expired_token_rejected():
    token = create_access_token("1", role="viewer", expires_delta=timedelta(seconds=-1))
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_token_rejected():
    token = create_access_token("1", role="viewer")
    with pytest.raises(TokenError):
        decode_access_token(token + "tamper")
