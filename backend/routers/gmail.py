import base64
import hashlib
import json
import os
import secrets
from datetime import timezone

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from services.gmail_service import encrypt_token, get_supabase

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _make_flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


def _generate_pkce() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(96)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def _get_user_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth[7:]
    supabase = get_supabase()
    result = supabase.auth.get_user(token)
    if not result or not result.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return result.user.id


@router.get("/auth-url")
async def get_auth_url(request: Request):
    user_id = _get_user_from_request(request)
    code_verifier, code_challenge = _generate_pkce()

    # Encode user_id + code_verifier in state
    state = base64.urlsafe_b64encode(
        json.dumps({"uid": user_id, "cv": code_verifier}).encode()
    ).decode()

    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def gmail_callback(request: Request):
    params = dict(request.query_params)
    state = params.get("state", "")
    code = params.get("code", "")

    try:
        state_data = json.loads(base64.urlsafe_b64decode(state + "==").decode())
        user_id = state_data["uid"]
        code_verifier = state_data["cv"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state")

    flow = _make_flow()
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials

    # Fetch Gmail address
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        userinfo = resp.json()
    gmail_email = userinfo.get("email", "")

    expiry = creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else None

    supabase = get_supabase()
    existing = supabase.table("gmail_accounts").select("id").eq("user_id", user_id).execute()
    if existing.data:
        supabase.table("gmail_accounts").update({
            "email": gmail_email,
            "access_token": encrypt_token(creds.token),
            "refresh_token": encrypt_token(creds.refresh_token) if creds.refresh_token else existing.data[0].get("refresh_token"),
            "token_expiry": expiry,
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("gmail_accounts").insert({
            "user_id": user_id,
            "email": gmail_email,
            "access_token": encrypt_token(creds.token),
            "refresh_token": encrypt_token(creds.refresh_token or ""),
            "token_expiry": expiry,
        }).execute()

    return RedirectResponse(url=f"{FRONTEND_URL}/link-email?status=success")
