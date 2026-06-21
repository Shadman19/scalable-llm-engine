"""Job status / result polling."""

from fastapi import APIRouter, HTTPException

from app.core import queue
from app.schemas import ChatResponse, JobStatus

router = APIRouter(prefix="/v1", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    job = await queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found or expired")

    result = job.get("result")
    return JobStatus(
        job_id=job_id,
        status=job.get("status", "queued"),
        result=ChatResponse(**result) if result else None,
        error=job.get("error"),
    )
