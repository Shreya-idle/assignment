import time

from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.database import Base, engine

app = FastAPI(
    title="AI Transaction Processing Pipeline",
    description="Upload CSV transactions for async cleaning, anomaly detection, and LLM analysis",
    version="1.0.0",
)

app.include_router(jobs_router)


@app.on_event("startup")
def startup():
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)


@app.get("/health")
def health():
    return {"status": "ok"}
