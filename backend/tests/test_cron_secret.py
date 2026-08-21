"""
Phase 1 eval: /scan/recurring is the one endpoint not gated by a user's
Supabase session — it's meant to be hit only by the pg_cron job, using a
shared secret. Anyone who guesses/leaks CRON_SECRET can trigger a scan
(and background Gmail/Gemini calls) for every linked account, so this
needs its own explicit coverage rather than piggybacking on test_auth.py.
"""
import routers.scan as scan_router
from tests.conftest import GMAIL_ACCOUNT_A, GMAIL_ACCOUNT_B


def test_recurring_scan_rejects_missing_header(client, monkeypatch):
    monkeypatch.setattr(scan_router, "CRON_SECRET", "real-secret")
    resp = client.post("/scan/recurring")
    assert resp.status_code == 401


def test_recurring_scan_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(scan_router, "CRON_SECRET", "real-secret")
    resp = client.post("/scan/recurring", headers={"Authorization": "Bearer wrong-secret"})
    assert resp.status_code == 401


def test_recurring_scan_rejects_empty_configured_secret(client, monkeypatch):
    # If CRON_SECRET is unset/empty in the environment, no bearer value should match it.
    monkeypatch.setattr(scan_router, "CRON_SECRET", "")
    resp = client.post("/scan/recurring", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


def test_recurring_scan_accepts_correct_secret(client, monkeypatch, fake_supabase):
    monkeypatch.setattr(scan_router, "CRON_SECRET", "real-secret")
    resp = client.post("/scan/recurring", headers={"Authorization": "Bearer real-secret"})
    assert resp.status_code == 200
    assert resp.json()["triggered"] == 2

    scan_jobs = fake_supabase.db["scan_jobs"]
    triggered_accounts = {
        j["gmail_account_id"] for j in scan_jobs if j["scan_type"] == "recurring"
    }
    assert triggered_accounts == {GMAIL_ACCOUNT_A, GMAIL_ACCOUNT_B}


def test_recurring_scan_skips_never_scanned_accounts(client, monkeypatch, fake_supabase):
    fake_supabase.db["gmail_accounts"].append(
        {
            "id": "cccccccc-0000-0000-0000-000000000003",
            "user_id": "33333333-3333-3333-3333-333333333333",
            "email": "c@example.com",
            "access_token": "enc-c-access",
            "refresh_token": "enc-c-refresh",
            "last_scanned_at": None,
        }
    )
    monkeypatch.setattr(scan_router, "CRON_SECRET", "real-secret")
    resp = client.post("/scan/recurring", headers={"Authorization": "Bearer real-secret"})
    assert resp.status_code == 200
    # Only the two already-scanned accounts should be triggered, not the brand-new one
    assert resp.json()["triggered"] == 2
