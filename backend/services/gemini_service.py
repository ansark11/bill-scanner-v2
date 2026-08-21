import os
import json
import logging
from typing import Optional

from google import genai

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

_EMPTY = {
    "biller_name": None,
    "account_number": None,
    "amount_due": None,
    "currency": None,
    "due_date": None,
    "sender_email": None,
}


def extract_bill_data(
    subject: str,
    sender: str,
    date_received: str,
    body: str,
    pdf_text: Optional[str] = None,
) -> dict:
    pdf_section = f"\nPDF attachment text:\n{pdf_text}" if pdf_text else ""
    prompt = f"""You are a bill extraction assistant. Given the following email content, extract
billing information and return ONLY a valid JSON object with these exact fields:

{{
  "biller_name": "string or null",
  "account_number": "string or null",
  "amount_due": number or null,
  "currency": "3-letter ISO code or null",
  "due_date": "YYYY-MM-DD or null",
  "sender_email": "string or null"
}}

Rules:
- Return null for any field you cannot confidently identify
- Return JSON only — no explanation, no markdown, no code fences
- due_date must be YYYY-MM-DD format or null
- amount_due must be a plain number (no currency symbols) or null

Email subject: {subject}
Email from: {sender}
Email date: {date_received}
Email body:
{body[:4000]}{pdf_section[:2000]}"""

    raw = ""
    try:
        response = _client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        logger.warning("Gemini extraction failed: %s | raw: %s", e, raw)
        return {**_EMPTY, "_raw": raw}
