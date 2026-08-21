"""
Phase 1 eval: Gmail OAuth tokens are stored encrypted at rest via
Fernet(key derived from OTP_SECRET_KEY). Covers the round trip and what
happens on a key rotation, since that's the kind of failure that only
shows up in production (every stored token becomes silently undecryptable).
"""
import pytest
from cryptography.fernet import InvalidToken

import services.gmail_service as gmail_service


@pytest.fixture(autouse=True)
def reset_fernet_cache(monkeypatch):
    # _get_fernet() memoizes the derived key in a module global; reset it
    # around each test so OTP_SECRET_KEY changes actually take effect.
    monkeypatch.setattr(gmail_service, "_fernet", None)
    yield
    monkeypatch.setattr(gmail_service, "_fernet", None)


def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setattr(gmail_service, "OTP_SECRET_KEY", "test-secret-key")
    token = "ya29.some-realistic-looking-access-token"
    encrypted = gmail_service.encrypt_token(token)
    assert encrypted != token
    assert gmail_service.decrypt_token(encrypted) == token


def test_encrypted_value_is_not_plaintext_substring(monkeypatch):
    monkeypatch.setattr(gmail_service, "OTP_SECRET_KEY", "test-secret-key")
    token = "1//refresh-token-value-should-not-leak"
    encrypted = gmail_service.encrypt_token(token)
    assert token not in encrypted


def test_decrypt_fails_after_key_rotation(monkeypatch):
    monkeypatch.setattr(gmail_service, "OTP_SECRET_KEY", "original-secret")
    token = "some-refresh-token"
    encrypted = gmail_service.encrypt_token(token)

    # Simulate rotating OTP_SECRET_KEY without a migration of already-stored tokens.
    monkeypatch.setattr(gmail_service, "_fernet", None)
    monkeypatch.setattr(gmail_service, "OTP_SECRET_KEY", "rotated-secret")

    with pytest.raises(InvalidToken):
        gmail_service.decrypt_token(encrypted)
