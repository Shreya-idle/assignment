from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JobUploadResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class JobStatusSummary(BaseModel):
    total_spend_inr: float | None = None
    total_spend_usd: float | None = None
    anomaly_count: int | None = None
    risk_level: str | None = None


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    filename: str
    row_count_raw: int
    row_count_clean: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    summary: JobStatusSummary | None = None


class TransactionOut(BaseModel):
    txn_id: str | None
    date: str
    merchant: str
    amount: float
    currency: str
    status: str
    category: str
    account_id: str
    notes: str | None = None
    is_anomaly: bool
    anomaly_reason: str | None = None
    llm_category: str | None = None
    llm_failed: bool = False

    model_config = {"from_attributes": True}


class AnomalyOut(BaseModel):
    txn_id: str | None
    merchant: str
    amount: float
    currency: str
    account_id: str
    anomaly_reason: str | None


class CategorySpendOut(BaseModel):
    category: str
    total_inr: float = 0.0
    total_usd: float = 0.0
    transaction_count: int


class JobSummaryOut(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: list[dict]
    anomaly_count: int
    narrative: str
    risk_level: str


class JobResultsResponse(BaseModel):
    job_id: UUID
    status: str
    transactions: list[TransactionOut]
    anomalies: list[AnomalyOut]
    category_breakdown: list[CategorySpendOut]
    summary: JobSummaryOut | None = None


class JobListItem(BaseModel):
    job_id: UUID
    status: str
    filename: str
    row_count_raw: int
    row_count_clean: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    total: int
