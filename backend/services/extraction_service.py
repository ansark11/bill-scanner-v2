import base64
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from services.gmail_service import get_valid_access_token, get_supabase
from services.gemini_service import extract_bill_data
from services.pdf_service import extract_pdf_text

logger = logging.getLogger(__name__)

CURRENCY_PATTERN = re.compile(
    r'(\$|€|£|¥|CAD|USD|EUR|GBP|AUD|CHF)\s*[\d,]+\.?\d*'
    r'|[\d,]+\.?\d*\s*(CAD|USD|EUR|GBP|AUD|CHF)',
    re.IGNORECASE,
)

BILL_KEYWORDS = re.compile(
    r'invoice|bill|statement|payment due|due date|amount due|'
    r'balance due|total due|pay by|due by',
    re.IGNORECASE,
)


def _decode_base64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "==")


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_body_and_attachments(payload: dict) -> tuple[str, list[dict]]:
    """Return (body_text, pdf_attachment_parts)."""
    body_text = ""
    attachments = []

    def walk(part):
        nonlocal body_text
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                body_text += _decode_base64(data).decode("utf-8", errors="ignore")
        elif mime == "text/html" and not body_text:
            data = part.get("body", {}).get("data", "")
            if data:
                html = _decode_base64(data).decode("utf-8", errors="ignore")
                body_text += re.sub(r"<[^>]+>", " ", html)
        elif mime == "application/pdf":
            attachments.append({
                "attachment_id": part.get("body", {}).get("attachmentId"),
                "filename": part.get("filename", ""),
            })
        for sub in part.get("parts", []):
            walk(sub)

    walk(payload)
    return body_text, attachments


async def run_pipeline(
    gmail_account_id: str,
    user_id: str,
    scan_job_id: str,
    scan_type: str,
    message_id_for_account: str,
):
    supabase = get_supabase()
    emails_scanned = 0
    bills_found = 0

    try:
        access_token = await get_valid_access_token(gmail_account_id)
        creds = Credentials(token=access_token)
        service = build("gmail", "v1", credentials=creds)

        # Determine date range
        if scan_type == "initial":
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        else:
            account_result = supabase.table("gmail_accounts").select("last_scanned_at").eq("id", gmail_account_id).single().execute()
            last_scanned = account_result.data.get("last_scanned_at")
            if last_scanned:
                start_date = datetime.fromisoformat(last_scanned.replace("Z", "+00:00"))
            else:
                start_date = datetime.now(timezone.utc) - timedelta(days=7)

        query = (
            "(invoice OR bill OR statement OR \"payment due\" OR \"due date\" "
            "OR \"amount due\" OR \"balance due\" OR \"total due\" OR \"pay by\" OR \"due by\") "
            f"after:{start_date.strftime('%Y/%m/%d')}"
        )

        # Fetch all matching message IDs
        message_ids = []
        page_token = None
        while True:
            params = {"userId": "me", "q": query, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            result = service.users().messages().list(**params).execute()
            message_ids.extend(result.get("messages", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        for msg_ref in message_ids:
            msg_id = msg_ref["id"]

            # Skip if already processed
            existing = supabase.table("bills").select("id").eq("email_message_id", msg_id).execute()
            if existing.data:
                continue

            emails_scanned += 1

            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                headers = msg.get("payload", {}).get("headers", [])
                subject = _get_header(headers, "subject")
                sender = _get_header(headers, "from")
                date_str = _get_header(headers, "date")
                try:
                    from email.utils import parsedate_to_datetime
                    date_received = parsedate_to_datetime(date_str).astimezone(timezone.utc)
                except Exception:
                    date_received = datetime.now(timezone.utc)

                body_text, pdf_parts = _extract_body_and_attachments(msg.get("payload", {}))

                # Currency filter
                amount_source = None
                pdf_text = None

                if CURRENCY_PATTERN.search(subject):
                    amount_source = "subject"
                elif CURRENCY_PATTERN.search(body_text):
                    amount_source = "body"
                elif pdf_parts:
                    for part in pdf_parts:
                        if not part.get("attachment_id"):
                            continue
                        att = service.users().messages().attachments().get(
                            userId="me", messageId=msg_id, id=part["attachment_id"]
                        ).execute()
                        pdf_bytes = _decode_base64(att.get("data", ""))
                        pdf_text = extract_pdf_text(pdf_bytes)
                        if CURRENCY_PATTERN.search(pdf_text):
                            amount_source = "attachment"
                            break

                if amount_source is None:
                    continue

                # LLM extraction
                extracted = extract_bill_data(subject, sender, date_str, body_text, pdf_text)
                raw_extraction = {k: v for k, v in extracted.items() if k != "_raw"}

                # Biller deduplication
                biller_id = None
                sender_email = extracted.get("sender_email") or _parse_email_address(sender)
                account_number = extracted.get("account_number")

                biller_query = supabase.table("billers").select("id").eq("user_id", user_id)
                if sender_email:
                    biller_query = biller_query.eq("sender_email", sender_email)
                if account_number:
                    biller_query = biller_query.eq("account_number", account_number)
                biller_result = biller_query.execute()

                if biller_result.data:
                    biller_id = biller_result.data[0]["id"]
                else:
                    biller_name = extracted.get("biller_name") or _extract_name_from_sender(sender)
                    new_biller = supabase.table("billers").insert({
                        "user_id": user_id,
                        "name": biller_name or "Unknown Biller",
                        "account_number": account_number,
                        "sender_email": sender_email,
                    }).execute()
                    biller_id = new_biller.data[0]["id"]

                # Insert bill
                due_date = extracted.get("due_date")
                amount_due = extracted.get("amount_due")
                currency = extracted.get("currency") or "CAD"

                supabase.table("bills").insert({
                    "user_id": user_id,
                    "biller_id": biller_id,
                    "gmail_account_id": gmail_account_id,
                    "email_message_id": msg_id,
                    "subject": subject,
                    "sender": sender,
                    "date_received": date_received.isoformat(),
                    "due_date": due_date,
                    "amount_due": amount_due,
                    "currency": currency,
                    "amount_source": amount_source,
                    "raw_extraction": raw_extraction,
                    "status": "pending",
                }).execute()
                bills_found += 1

            except Exception as e:
                logger.warning("Error processing email %s: %s", msg_id, e)
                continue

        # Update last_scanned_at
        supabase.table("gmail_accounts").update({
            "last_scanned_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", gmail_account_id).execute()

        # Complete scan job
        supabase.table("scan_jobs").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "emails_scanned": emails_scanned,
            "bills_found": bills_found,
        }).eq("id", scan_job_id).execute()

    except Exception as e:
        logger.error("Pipeline failed for account %s: %s", gmail_account_id, e)
        supabase.table("scan_jobs").update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }).eq("id", scan_job_id).execute()


def _parse_email_address(sender: str) -> Optional[str]:
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).lower()
    if "@" in sender:
        return sender.strip().lower()
    return None


def _extract_name_from_sender(sender: str) -> Optional[str]:
    match = re.match(r'^"?([^"<]+)"?\s*<', sender)
    if match:
        return match.group(1).strip()
    return None
