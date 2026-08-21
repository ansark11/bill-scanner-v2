import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from models.schemas import ScanInitialRequest
from services.gmail_service import get_supabase
from services.extraction_service import run_pipeline

router = APIRouter()

CRON_SECRET = os.getenv("CRON_SECRET", "")


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


@router.post("/initial")
async def scan_initial(body: ScanInitialRequest, request: Request, background_tasks: BackgroundTasks):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()

    # Verify the gmail_account belongs to this user
    account = supabase.table("gmail_accounts").select("id").eq("id", body.gmail_account_id).eq("user_id", user_id).execute()
    if not account.data:
        raise HTTPException(status_code=404, detail="Gmail account not found")

    # Create scan job
    job = supabase.table("scan_jobs").insert({
        "gmail_account_id": body.gmail_account_id,
        "user_id": user_id,
        "scan_type": "initial",
        "status": "running",
    }).execute()
    scan_job_id = job.data[0]["id"]

    background_tasks.add_task(
        run_pipeline,
        body.gmail_account_id,
        user_id,
        scan_job_id,
        "initial",
        body.gmail_account_id,
    )

    return {"scan_job_id": scan_job_id}


@router.post("/recurring")
async def scan_recurring(request: Request, background_tasks: BackgroundTasks):
    auth = request.headers.get("authorization", "")
    if not CRON_SECRET or auth != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    supabase = get_supabase()
    accounts = supabase.table("gmail_accounts").select("*").not_.is_("last_scanned_at", "null").execute()

    for account in accounts.data:
        job = supabase.table("scan_jobs").insert({
            "gmail_account_id": account["id"],
            "user_id": account["user_id"],
            "scan_type": "recurring",
            "status": "running",
        }).execute()
        scan_job_id = job.data[0]["id"]

        background_tasks.add_task(
            run_pipeline,
            account["id"],
            account["user_id"],
            scan_job_id,
            "recurring",
            account["id"],
        )

    return {"triggered": len(accounts.data)}


@router.get("/status/{scan_job_id}")
async def scan_status(scan_job_id: str, request: Request):
    user_id = _get_user_from_request(request)
    supabase = get_supabase()
    result = supabase.table("scan_jobs").select("*").eq("id", scan_job_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Scan job not found")
    job = result.data[0]
    # Auto-fail jobs stuck in running for >15 minutes (e.g. process was killed)
    if job["status"] == "running" and job.get("started_at"):
        started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - started).total_seconds() > 900:
            supabase.table("scan_jobs").update({"status": "failed", "error": "Timed out"}).eq("id", scan_job_id).execute()
            job["status"] = "failed"
            job["error"] = "Timed out"
    return job
