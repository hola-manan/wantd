"""HTTP API. Run: uvicorn wantd.api:app --reload

    POST /extract {"url": "..."}  -> 202 {id, status}   (same reel again -> same job)
    GET  /extract/{id}            -> {status, stage, result, error}
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

from wantd import pipeline
from wantd.fetch import normalize_video_url
from wantd.schema import Result

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Wantd API", version="0.1.0")

# ponytail: in-memory jobs + cache, lost on restart. Move to Firestore/Cloud Tasks when deployed.
_jobs: dict[str, dict] = {}
_by_url: dict[str, str] = {}
_lock = Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wantd")


class ExtractRequest(BaseModel):
    url: HttpUrl          # URLs only: never let a client point the pipeline at a server file
    max_tier: int = 3


class Job(BaseModel):
    id: str
    url: str
    status: str           # queued | running | done | failed
    stage: str = ""
    result: Result | None = None
    error: str | None = None


def _work(job_id: str, max_tier: int) -> None:
    job = _jobs[job_id]
    job["status"] = "running"

    def stage(s: str) -> None:
        job["stage"] = s

    try:
        job["result"] = pipeline.run(job["url"], max_tier=max_tier, on_stage=stage)
        job["status"] = "done"
    except Exception as e:
        logging.exception("job %s failed", job_id)
        job["status"], job["error"] = "failed", str(e)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/extract", response_model=Job, status_code=202)
def extract(req: ExtractRequest):
    url = normalize_video_url(str(req.url))
    with _lock:
        # Each reel is analysed once and reused, unless the earlier attempt failed.
        existing = _by_url.get(url)
        if existing and _jobs[existing]["status"] != "failed":
            return _jobs[existing]
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {"id": job_id, "url": url, "status": "queued", "stage": "",
                         "result": None, "error": None}
        _by_url[url] = job_id
    _pool.submit(_work, job_id, req.max_tier)
    return _jobs[job_id]


@app.get("/extract/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job
