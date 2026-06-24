import logging
import uuid
from datetime import datetime

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, JobSummary, Transaction
from app.services.anomaly import detect_anomalies
from app.services.cleaning import clean_transactions
from app.services.llm import classify_categories_batch, generate_narrative_summary

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.process_job")
def process_job(self, job_id: str, raw_rows: list[dict[str, str]]):
    db = SessionLocal()
    job_uuid = uuid.UUID(job_id)

    try:
        job = db.query(Job).filter(Job.id == job_uuid).first()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        job.status = "processing"
        db.commit()

        cleaned = clean_transactions(raw_rows)
        cleaned = detect_anomalies(cleaned)
        cleaned, _, _ = classify_categories_batch(cleaned)
        summary_data, _, _ = generate_narrative_summary(cleaned)

        for txn in cleaned:
            db.add(
                Transaction(
                    job_id=job_uuid,
                    txn_id=txn.get("txn_id"),
                    date=txn["date"],
                    merchant=txn["merchant"],
                    amount=txn["amount"],
                    currency=txn["currency"],
                    status=txn["status"],
                    category=txn["category"],
                    account_id=txn["account_id"],
                    notes=txn.get("notes"),
                    is_anomaly=txn.get("is_anomaly", False),
                    anomaly_reason=txn.get("anomaly_reason"),
                    llm_category=txn.get("llm_category"),
                    llm_raw_response=txn.get("llm_raw_response"),
                    llm_failed=txn.get("llm_failed", False),
                )
            )

        db.add(
            JobSummary(
                job_id=job_uuid,
                total_spend_inr=summary_data["total_spend_inr"],
                total_spend_usd=summary_data["total_spend_usd"],
                top_merchants=summary_data["top_merchants"],
                anomaly_count=summary_data["anomaly_count"],
                narrative=summary_data["narrative"],
                risk_level=summary_data["risk_level"],
            )
        )

        job.status = "completed"
        job.row_count_clean = len(cleaned)
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        db.rollback()
        job = db.query(Job).filter(Job.id == job_uuid).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
