from datetime import date
from calendar import monthrange

from fastapi import APIRouter, HTTPException, Request

from models.schemas import ConfirmBillsRequest
from services.gmail_service import get_supabase

router = APIRouter()


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


@router.get("/current-month")
async def get_current_month_bills(request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()

    today = date.today()
    first_day = today.replace(day=1).isoformat()
    last_day = today.replace(day=monthrange(today.year, today.month)[1]).isoformat()

    result = (
        supabase.table("bills")
        .select("*, billers(name, account_number)")
        .eq("user_id", user_id)
        .eq("status", "confirmed")
        .gte("due_date", first_day)
        .lte("due_date", last_day)
        .order("due_date", desc=False)
        .execute()
    )

    bills = []
    for b in result.data:
        biller = b.pop("billers", {}) or {}
        bills.append({**b, "biller_name": biller.get("name"), "biller_account_number": biller.get("account_number")})
    return bills


@router.get("/pending")
async def get_pending_bills(request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()

    result = (
        supabase.table("bills")
        .select("*, billers(name, account_number)")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )

    bills = []
    for b in result.data:
        biller = b.pop("billers", {}) or {}
        bills.append({**b, "biller_name": biller.get("name"), "biller_account_number": biller.get("account_number")})
    return bills


@router.patch("/confirm")
async def confirm_bills(body: ConfirmBillsRequest, request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()

    all_ids = body.confirmed_bill_ids + body.ignored_bill_ids
    if all_ids:
        # Verify ownership
        owned = supabase.table("bills").select("id").eq("user_id", user_id).in_("id", all_ids).execute()
        owned_ids = {r["id"] for r in owned.data}
        if len(owned_ids) != len(all_ids):
            raise HTTPException(status_code=403, detail="One or more bill IDs not authorized")

    if body.confirmed_bill_ids:
        supabase.table("bills").update({"status": "confirmed"}).in_("id", body.confirmed_bill_ids).execute()
    if body.ignored_bill_ids:
        supabase.table("bills").update({"status": "ignored"}).in_("id", body.ignored_bill_ids).execute()

    return {"ok": True}


@router.get("/billers")
async def get_billers(request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()
    result = supabase.table("billers").select("*").eq("user_id", user_id).order("name").execute()
    return result.data


@router.get("/billers/{biller_id}")
async def get_biller(biller_id: str, request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()
    result = supabase.table("billers").select("*").eq("id", biller_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Biller not found")
    return result.data[0]


@router.delete("/billers/{biller_id}", status_code=204)
async def delete_biller(biller_id: str, request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()

    # Verify ownership
    result = supabase.table("billers").select("id").eq("id", biller_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Biller not found")

    # Delete bills first (cascade), then biller
    supabase.table("bills").delete().eq("biller_id", biller_id).execute()
    supabase.table("billers").delete().eq("id", biller_id).execute()
