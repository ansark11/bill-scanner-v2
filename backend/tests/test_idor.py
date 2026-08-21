"""
Phase 1 eval: cross-user data access (IDOR) and data-isolation checks.

The backend talks to Supabase with the *service role key* (see
services/gmail_service.py get_supabase), which bypasses row-level security
entirely. That means the `user_id` filter baked into each query is the only
thing standing between one user and another user's bills/billers/tokens.
These tests exist to catch a missing or wrong filter, not just a wrong
status code.
"""
from tests.conftest import (
    auth_header,
    TOKEN_A,
    TOKEN_B,
    GMAIL_ACCOUNT_A,
    GMAIL_ACCOUNT_B,
    BILLER_A,
    BILLER_B,
    BILL_A,
    BILL_B,
    CONFIRMED_BILL_A,
    CONFIRMED_BILL_B,
    SCAN_JOB_A,
    SCAN_JOB_B,
)


def test_scan_initial_rejects_other_users_gmail_account(client):
    resp = client.post(
        "/scan/initial",
        json={"gmail_account_id": GMAIL_ACCOUNT_A},
        headers=auth_header(TOKEN_B),
    )
    assert resp.status_code == 404


def test_scan_initial_accepts_own_gmail_account(client):
    resp = client.post(
        "/scan/initial",
        json={"gmail_account_id": GMAIL_ACCOUNT_A},
        headers=auth_header(TOKEN_A),
    )
    assert resp.status_code == 200
    assert "scan_job_id" in resp.json()


def test_scan_status_rejects_other_users_job(client):
    resp = client.get(f"/scan/status/{SCAN_JOB_B}", headers=auth_header(TOKEN_A))
    assert resp.status_code == 404


def test_scan_status_allows_own_job(client):
    resp = client.get(f"/scan/status/{SCAN_JOB_A}", headers=auth_header(TOKEN_A))
    assert resp.status_code == 200
    assert resp.json()["id"] == SCAN_JOB_A


def test_confirm_bills_rejects_other_users_bill_id(client):
    resp = client.patch(
        "/bills/confirm",
        json={"confirmed_bill_ids": [BILL_A], "ignored_bill_ids": []},
        headers=auth_header(TOKEN_B),
    )
    assert resp.status_code == 403


def test_confirm_bills_does_not_mutate_unauthorized_bill(client, fake_supabase):
    client.patch(
        "/bills/confirm",
        json={"confirmed_bill_ids": [BILL_A], "ignored_bill_ids": []},
        headers=auth_header(TOKEN_B),
    )
    bill_a = next(b for b in fake_supabase.db["bills"] if b["id"] == BILL_A)
    assert bill_a["status"] == "pending"  # unchanged despite the attempted cross-user confirm


def test_confirm_bills_allows_own_bill(client):
    resp = client.patch(
        "/bills/confirm",
        json={"confirmed_bill_ids": [BILL_A], "ignored_bill_ids": []},
        headers=auth_header(TOKEN_A),
    )
    assert resp.status_code == 200


def test_get_biller_rejects_other_users_biller(client):
    resp = client.get(f"/bills/billers/{BILLER_A}", headers=auth_header(TOKEN_B))
    assert resp.status_code == 404


def test_get_biller_allows_own_biller(client):
    resp = client.get(f"/bills/billers/{BILLER_A}", headers=auth_header(TOKEN_A))
    assert resp.status_code == 200
    assert resp.json()["id"] == BILLER_A


def test_delete_biller_rejects_other_users_biller(client, fake_supabase):
    resp = client.delete(f"/bills/billers/{BILLER_A}", headers=auth_header(TOKEN_B))
    assert resp.status_code == 404
    # confirm nothing was actually deleted
    assert any(b["id"] == BILLER_A for b in fake_supabase.db["billers"])
    assert any(b["id"] == BILL_A for b in fake_supabase.db["bills"])


def test_delete_biller_cascades_only_own_bills(client, fake_supabase):
    resp = client.delete(f"/bills/billers/{BILLER_A}", headers=auth_header(TOKEN_A))
    assert resp.status_code == 204
    remaining_bill_ids = {b["id"] for b in fake_supabase.db["bills"]}
    assert BILL_A not in remaining_bill_ids
    assert CONFIRMED_BILL_A not in remaining_bill_ids
    # user B's data must be untouched
    assert BILL_B in remaining_bill_ids
    assert CONFIRMED_BILL_B in remaining_bill_ids
    assert any(b["id"] == BILLER_B for b in fake_supabase.db["billers"])


def test_pending_bills_isolated_per_user(client):
    resp_a = client.get("/bills/pending", headers=auth_header(TOKEN_A))
    resp_b = client.get("/bills/pending", headers=auth_header(TOKEN_B))
    ids_a = {b["id"] for b in resp_a.json()}
    ids_b = {b["id"] for b in resp_b.json()}
    assert BILL_A in ids_a and BILL_B not in ids_a
    assert BILL_B in ids_b and BILL_A not in ids_b


def test_current_month_bills_isolated_per_user(client):
    resp_a = client.get("/bills/current-month", headers=auth_header(TOKEN_A))
    resp_b = client.get("/bills/current-month", headers=auth_header(TOKEN_B))
    ids_a = {b["id"] for b in resp_a.json()}
    ids_b = {b["id"] for b in resp_b.json()}
    assert CONFIRMED_BILL_A in ids_a and CONFIRMED_BILL_B not in ids_a
    assert CONFIRMED_BILL_B in ids_b and CONFIRMED_BILL_A not in ids_b


def test_billers_list_isolated_per_user(client):
    resp_a = client.get("/bills/billers", headers=auth_header(TOKEN_A))
    resp_b = client.get("/bills/billers", headers=auth_header(TOKEN_B))
    ids_a = {b["id"] for b in resp_a.json()}
    ids_b = {b["id"] for b in resp_b.json()}
    assert BILLER_A in ids_a and BILLER_B not in ids_a
    assert BILLER_B in ids_b and BILLER_A not in ids_b
