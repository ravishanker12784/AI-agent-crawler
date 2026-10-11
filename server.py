"""
Trigger layer for the scraping agent.
  - REST API:   POST /run  (start a job), GET /jobs/{id}, GET /jobs
  - Scheduler:  reads schedules.json and runs jobs on cron times
Run:  uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import json
import uuid
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from agent import run_agent

load_dotenv()
API_KEY = os.getenv("AGENT_API_KEY")  # optional but recommended
SCHEDULE_FILE = Path(os.getenv("SCHEDULE_FILE", "schedules.json"))

executor = ThreadPoolExecutor(max_workers=int(os.getenv("MAX_WORKERS", "2")))
jobs: dict[str, dict] = {}
lock = threading.Lock()
scheduler = BackgroundScheduler()


class RunRequest(BaseModel):
    goal: str
    start_url: str | None = None
    fields: list[str] | None = None
    max_steps: int = 25


def _execute(job_id: str, req: dict):
    logs = []
    with lock:
        jobs[job_id]["status"] = "running"
    try:
        result = run_agent(req["goal"], req.get("start_url"), req.get("fields"),
                           req.get("max_steps", 25), log=logs.append)
        with lock:
            jobs[job_id].update(status="done", result=result, logs=logs)
    except Exception as e:
        with lock:
            jobs[job_id].update(status="failed", error=str(e), logs=logs)


def submit(req: dict, source="api") -> str:
    job_id = uuid.uuid4().hex[:8]
    with lock:
        jobs[job_id] = {"id": job_id, "status": "queued", "source": source, "request": req}
    executor.submit(_execute, job_id, req)
    return job_id


def load_schedules():
    if not SCHEDULE_FILE.exists():
        return
    for item in json.loads(SCHEDULE_FILE.read_text()):
        if not item.get("enabled", True):
            continue
        req = {k: item.get(k) for k in ("goal", "start_url", "fields")}
        req["max_steps"] = item.get("max_steps", 25)
        scheduler.add_job(submit, CronTrigger.from_crontab(item["cron"]),
                          args=[req, f"schedule:{item.get('name', 'unnamed')}"],
                          id=item.get("name"), replace_existing=True)
        print(f"Scheduled '{item.get('name')}' at cron '{item['cron']}'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_schedules()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Scraper Agent", lifespan=lifespan)


def check_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Invalid or missing X-API-Key")


@app.post("/run")
def run(req: RunRequest, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    return {"job_id": submit(req.model_dump(), "api"), "status": "queued"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/jobs")
def list_jobs(x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    return [{"id": j["id"], "status": j["status"], "source": j["source"]} for j in jobs.values()]


@app.get("/health")
def health():
    return {"ok": True, "scheduled": [j.id for j in scheduler.get_jobs()]}
