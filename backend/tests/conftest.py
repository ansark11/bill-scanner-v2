import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Modules under test (routers/scan.py -> services/gemini_service.py) read API
# keys from the environment at import time, so this has to load before any
# test module imports them — pytest imports conftest.py first, which is why
# this lives here rather than in each test file.
from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

import pytest
from fastapi.testclient import TestClient

from tests.fake_supabase import FakeSupabase

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
TOKEN_A = "token-for-user-a"
TOKEN_B = "token-for-user-b"

GMAIL_ACCOUNT_A = "aaaaaaaa-0000-0000-0000-000000000001"
GMAIL_ACCOUNT_B = "bbbbbbbb-0000-0000-0000-000000000002"
BILLER_A = "aaaaaaaa-0000-0000-0000-000000000010"
BILLER_B = "bbbbbbbb-0000-0000-0000-000000000020"
BILL_A = "aaaaaaaa-0000-0000-0000-000000000100"
BILL_B = "bbbbbbbb-0000-0000-0000-000000000200"
SCAN_JOB_A = "aaaaaaaa-0000-0000-0000-000000001000"
SCAN_JOB_B = "bbbbbbbb-0000-0000-0000-000000002000"
CONFIRMED_BILL_A = "aaaaaaaa-0000-0000-0000-000000000101"
CONFIRMED_BILL_B = "bbbbbbbb-0000-0000-0000-000000000201"


def seeded_db() -> dict:
    """Two-user dataset: everything about user A must stay invisible to user B."""
    today = date.today().isoformat()
    return {
        "gmail_accounts": [
            {
                "id": GMAIL_ACCOUNT_A,
                "user_id": USER_A,
                "email": "a@example.com",
                "access_token": "enc-a-access",
                "refresh_token": "enc-a-refresh",
                "last_scanned_at": "2026-08-01T00:00:00+00:00",
            },
            {
                "id": GMAIL_ACCOUNT_B,
                "user_id": USER_B,
                "email": "b@example.com",
                "access_token": "enc-b-access",
                "refresh_token": "enc-b-refresh",
                "last_scanned_at": "2026-08-01T00:00:00+00:00",
            },
        ],
        "billers": [
            {
                "id": BILLER_A,
                "user_id": USER_A,
                "name": "Acme Power",
                "account_number": "ACC-A",
                "sender_email": "billing@acme.example",
            },
            {
                "id": BILLER_B,
                "user_id": USER_B,
                "name": "Beta Telecom",
                "account_number": "ACC-B",
                "sender_email": "billing@beta.example",
            },
        ],
        "bills": [
            {
                "id": BILL_A,
                "user_id": USER_A,
                "biller_id": BILLER_A,
                "gmail_account_id": GMAIL_ACCOUNT_A,
                "email_message_id": "msg-a-1",
                "subject": "Your Acme bill",
                "sender": "billing@acme.example",
                "date_received": "2026-08-10T00:00:00+00:00",
                "due_date": "2026-08-25",
                "amount_due": 42.50,
                "currency": "CAD",
                "amount_source": "body",
                "status": "pending",
                "created_at": "2026-08-10T00:00:00+00:00",
            },
            {
                "id": BILL_B,
                "user_id": USER_B,
                "biller_id": BILLER_B,
                "gmail_account_id": GMAIL_ACCOUNT_B,
                "email_message_id": "msg-b-1",
                "subject": "Your Beta bill",
                "sender": "billing@beta.example",
                "date_received": "2026-08-11T00:00:00+00:00",
                "due_date": "2026-08-26",
                "amount_due": 88.00,
                "currency": "CAD",
                "amount_source": "body",
                "status": "pending",
                "created_at": "2026-08-11T00:00:00+00:00",
            },
            {
                "id": CONFIRMED_BILL_A,
                "user_id": USER_A,
                "biller_id": BILLER_A,
                "gmail_account_id": GMAIL_ACCOUNT_A,
                "email_message_id": "msg-a-2",
                "subject": "Acme bill (confirmed)",
                "sender": "billing@acme.example",
                "date_received": "2026-08-05T00:00:00+00:00",
                "due_date": today,
                "amount_due": 12.00,
                "currency": "CAD",
                "amount_source": "body",
                "status": "confirmed",
                "created_at": "2026-08-05T00:00:00+00:00",
            },
            {
                "id": CONFIRMED_BILL_B,
                "user_id": USER_B,
                "biller_id": BILLER_B,
                "gmail_account_id": GMAIL_ACCOUNT_B,
                "email_message_id": "msg-b-2",
                "subject": "Beta bill (confirmed)",
                "sender": "billing@beta.example",
                "date_received": "2026-08-06T00:00:00+00:00",
                "due_date": today,
                "amount_due": 24.00,
                "currency": "CAD",
                "amount_source": "body",
                "status": "confirmed",
                "created_at": "2026-08-06T00:00:00+00:00",
            },
        ],
        "scan_jobs": [
            {
                "id": SCAN_JOB_A,
                "gmail_account_id": GMAIL_ACCOUNT_A,
                "user_id": USER_A,
                "scan_type": "initial",
                "started_at": "2026-08-20T00:00:00+00:00",
                "completed_at": None,
                "emails_scanned": 0,
                "bills_found": 0,
                "status": "running",
                "error": None,
            },
            {
                "id": SCAN_JOB_B,
                "gmail_account_id": GMAIL_ACCOUNT_B,
                "user_id": USER_B,
                "scan_type": "initial",
                "started_at": "2026-08-20T00:00:00+00:00",
                "completed_at": None,
                "emails_scanned": 0,
                "bills_found": 0,
                "status": "running",
                "error": None,
            },
        ],
    }


@pytest.fixture
def fake_supabase(monkeypatch):
    db = seeded_db()
    fake = FakeSupabase(db=db, valid_tokens={TOKEN_A: USER_A, TOKEN_B: USER_B})

    import routers.gmail as gmail_router
    import routers.scan as scan_router
    import routers.bills as bills_router
    import services.gmail_service as gmail_service

    for mod in (gmail_router, scan_router, bills_router, gmail_service):
        monkeypatch.setattr(mod, "get_supabase", lambda f=fake: f)

    async def _noop_pipeline(*args, **kwargs):
        return None

    monkeypatch.setattr(scan_router, "run_pipeline", _noop_pipeline)

    return fake


@pytest.fixture
def client(fake_supabase):
    from main import app

    with TestClient(app) as c:
        yield c


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
