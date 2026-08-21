from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from uuid import UUID


class ScanInitialRequest(BaseModel):
    gmail_account_id: str


class ConfirmBillsRequest(BaseModel):
    confirmed_bill_ids: list[str]
    ignored_bill_ids: list[str]


class BillOut(BaseModel):
    id: str
    biller_id: Optional[str]
    biller_name: Optional[str]
    account_number: Optional[str]
    email_message_id: str
    subject: Optional[str]
    sender: Optional[str]
    date_received: Optional[datetime]
    due_date: Optional[date]
    amount_due: Optional[float]
    currency: Optional[str]
    amount_source: Optional[str]
    status: str
    created_at: datetime


class BillerOut(BaseModel):
    id: str
    name: str
    account_number: Optional[str]
    sender_email: Optional[str]
    created_at: datetime


class ScanJobOut(BaseModel):
    id: str
    gmail_account_id: str
    user_id: str
    scan_type: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    emails_scanned: int
    bills_found: int
    status: str
    error: Optional[str]
