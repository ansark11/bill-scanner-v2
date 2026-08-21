import os
import base64
from datetime import datetime, timezone, timedelta

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OTP_SECRET_KEY = os.getenv("OTP_SECRET_KEY", "")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"bill_wrangler_salt",
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(OTP_SECRET_KEY.encode()))
        _fernet = Fernet(key)
    return _fernet


def encrypt_token(token: str) -> str:
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


async def get_valid_access_token(gmail_account_id: str) -> str:
    supabase = get_supabase()
    result = supabase.table("gmail_accounts").select("*").eq("id", gmail_account_id).single().execute()
    account = result.data

    expiry = None
    if account.get("token_expiry"):
        expiry = datetime.fromisoformat(account["token_expiry"].replace("Z", "+00:00"))

    needs_refresh = expiry is None or expiry <= datetime.now(timezone.utc) + timedelta(minutes=5)

    if needs_refresh:
        creds = Credentials(
            token=decrypt_token(account["access_token"]),
            refresh_token=decrypt_token(account["refresh_token"]),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        creds.refresh(Request())
        new_expiry = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None
        supabase.table("gmail_accounts").update({
            "access_token": encrypt_token(creds.token),
            "token_expiry": new_expiry.isoformat() if new_expiry else None,
        }).eq("id", gmail_account_id).execute()
        return creds.token

    return decrypt_token(account["access_token"])
