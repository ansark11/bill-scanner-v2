"""
Phase 1 eval: every protected route must reject requests with a missing,
malformed, or unrecognized bearer token. Each router re-implements
_get_user_from_request independently (gmail.py, scan.py, bills.py) so this
has to be checked per-router, not assumed from one working example.
"""
import pytest

from tests.conftest import GMAIL_ACCOUNT_A, SCAN_JOB_A, BILLER_A

PROTECTED_ROUTES = [
    ("get", "/gmail/auth-url", None),
    ("post", "/scan/initial", {"gmail_account_id": GMAIL_ACCOUNT_A}),
    ("get", f"/scan/status/{SCAN_JOB_A}", None),
    ("get", "/bills/current-month", None),
    ("get", "/bills/pending", None),
    ("patch", "/bills/confirm", {"confirmed_bill_ids": [], "ignored_bill_ids": []}),
    ("get", "/bills/billers", None),
    ("get", f"/bills/billers/{BILLER_A}", None),
    ("delete", f"/bills/billers/{BILLER_A}", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_missing_auth_header_rejected(client, method, path, body):
    resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_malformed_auth_header_rejected(client, method, path, body):
    headers = {"Authorization": "not-a-bearer-token"}
    resp = (
        getattr(client, method)(path, json=body, headers=headers)
        if body is not None
        else getattr(client, method)(path, headers=headers)
    )
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_unknown_token_rejected(client, method, path, body):
    headers = {"Authorization": "Bearer this-token-does-not-exist"}
    resp = (
        getattr(client, method)(path, json=body, headers=headers)
        if body is not None
        else getattr(client, method)(path, headers=headers)
    )
    assert resp.status_code == 401
