from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Job
from app.schemas import (
    AnomalyOut,
    CategorySpendOut,
    JobListItem,
    JobListResponse,
    JobResultsResponse,
    JobStatusResponse,
    JobStatusSummary,
    JobSummaryOut,
    JobUploadResponse,
    TransactionOut,
)
from app.services.cleaning import parse_csv
from app.services.llm import build_category_breakdown
from app.tasks.pipeline import process_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=JobUploadResponse, status_code=202)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        rows, _ = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=400, detail="CSV contains no data rows")

    job = Job(filename=file.filename, status="pending", row_count_raw=len(rows))
    db.add(job)
    db.commit()
    db.refresh(job)

    process_job.delay(str(job.id), rows)

    return JobUploadResponse(
        job_id=job.id,
        status=job.status,
        message="Job enqueued for processing",
    )


@router.get("", response_model=JobListResponse)
def list_jobs(
    status: str | None = Query(None, description="Filter by job status"),
    db: Session = Depends(get_db),
):
    query = db.query(Job).order_by(Job.created_at.desc())
    if status:
        query = query.filter(Job.status == status.lower())

    jobs = query.all()
    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=j.id,
                status=j.status,
                filename=j.filename,
                row_count_raw=j.row_count_raw,
                row_count_clean=j.row_count_clean,
                created_at=j.created_at,
            )
            for j in jobs
        ],
        total=len(jobs),
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: UUID, db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.summary))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = None
    if job.status == "completed" and job.summary:
        summary = JobStatusSummary(
            total_spend_inr=job.summary.total_spend_inr,
            total_spend_usd=job.summary.total_spend_usd,
            anomaly_count=job.summary.anomaly_count,
            risk_level=job.summary.risk_level,
        )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: UUID, db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.summary), joinedload(Job.transactions))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed yet (current status: {job.status})",
        )

    txn_dicts = [
        {
            "category": t.category,
            "currency": t.currency,
            "amount": t.amount,
        }
        for t in job.transactions
    ]
    breakdown = build_category_breakdown(txn_dicts)

    anomalies = [
        AnomalyOut(
            txn_id=t.txn_id,
            merchant=t.merchant,
            amount=t.amount,
            currency=t.currency,
            account_id=t.account_id,
            anomaly_reason=t.anomaly_reason,
        )
        for t in job.transactions
        if t.is_anomaly
    ]

    summary_out = None
    if job.summary:
        summary_out = JobSummaryOut(
            total_spend_inr=job.summary.total_spend_inr,
            total_spend_usd=job.summary.total_spend_usd,
            top_merchants=job.summary.top_merchants,
            anomaly_count=job.summary.anomaly_count,
            narrative=job.summary.narrative,
            risk_level=job.summary.risk_level,
        )

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        transactions=[TransactionOut.model_validate(t) for t in job.transactions],
        anomalies=anomalies,
        category_breakdown=[CategorySpendOut(**b) for b in breakdown],
        summary=summary_out,
    )
