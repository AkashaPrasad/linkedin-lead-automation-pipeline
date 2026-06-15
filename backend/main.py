import asyncio
import json
import sys
from datetime import date as dt_date
from pathlib import Path
from collections import deque
from contextlib import asynccontextmanager

import requests as req
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from config import validate_config, GOOGLE_SHEET_ID, service_account_path
from logger import get_logger
from pipeline import run_pipeline_async, resume_pipeline_async
import admin_config as admin_cfg
import checkpoint as cp
import run_history
import scheduler as sched

log = get_logger("main")

# ── SSE state ────────────────────────────────────────────────────────────────
_subscribers: list[asyncio.Queue] = []
_event_history: deque = deque(maxlen=500)
_is_running = False


async def broadcast(event: dict):
    _event_history.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def _pipeline_run_core(wrapper_fn):
    """Runs the pipeline, captures history, resets _is_running."""
    global _is_running
    last_stats: dict = {}
    complete_data: dict | None = None

    async def _capturing_emit(event: dict):
        nonlocal complete_data
        await broadcast(event)
        if event.get("event") == "stats":
            last_stats.update(event)
        elif event.get("event") == "complete":
            complete_data = event

    try:
        await wrapper_fn(_capturing_emit)
    finally:
        _is_running = False
        if complete_data:
            run_history.append_run({
                "scraped": complete_data.get("scraped", 0),
                "real": complete_data.get("real", 0),
                "enriched": last_stats.get("enriched", 0),
                "with_email": complete_data.get("with_email", 0),
                "sent": complete_data.get("sent", 0),
                "failed": complete_data.get("failed", 0),
                "no_email": complete_data.get("no_email", 0),
                "duration_min": complete_data.get("duration_min", 0),
                "dry_run": complete_data.get("dry_run", False),
                "date": dt_date.today().isoformat(),
            })


async def _pipeline_wrapper():
    await _pipeline_run_core(run_pipeline_async)


async def _scheduled_pipeline_run():
    global _is_running
    if _is_running:
        log.info("Scheduled run skipped — pipeline already running")
        return
    _is_running = True
    _event_history.clear()
    log.info("Scheduled pipeline run starting")
    await _pipeline_run_core(run_pipeline_async)


# ── Startup / shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = validate_config()
    if not service_account_path().exists():
        log.error("STARTUP FAILED: service_account.json not found in backend/ folder")
    elif missing:
        log.error(f"STARTUP FAILED: Missing env vars: {', '.join(missing)}")
    else:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(service_account_path()), scopes=scopes)
            gc = gspread.authorize(creds)
            gc.open_by_key(GOOGLE_SHEET_ID)
            log.info("✅ All checks passed — Decision Pinnacle Pipeline ready")
        except Exception as e:
            log.error(f"Google Sheets connection test failed: {e}")

    # Start scheduler and apply saved automation config
    sched.init(_scheduled_pipeline_run)
    cfg = admin_cfg.load()
    sched.update(cfg.get("automation", {}))

    yield

    sched.shutdown()


app = FastAPI(title="Decision Pinnacle Pipeline", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── SSE endpoint ─────────────────────────────────────────────────────────────
@app.get("/api/pipeline/stream")
async def pipeline_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.append(q)

    async def generate():
        for event in list(_event_history):
            yield {"data": json.dumps(event)}
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"data": json.dumps(event)}
                    if event.get("event") in ["complete", "error"]:
                        break
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"event": "heartbeat"})}
        finally:
            if q in _subscribers:
                _subscribers.remove(q)

    return EventSourceResponse(generate())


# ── Pipeline run endpoint ─────────────────────────────────────────────────────
@app.post("/api/pipeline/run")
async def run_pipeline(background_tasks: BackgroundTasks):
    global _is_running
    if _is_running:
        raise HTTPException(status_code=409, detail="Pipeline already in progress")
    missing = validate_config()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing env vars: {', '.join(missing)}")
    if not service_account_path().exists():
        raise HTTPException(status_code=400, detail="service_account.json not found in backend/ folder")
    _is_running = True
    _event_history.clear()
    background_tasks.add_task(_pipeline_wrapper)
    return {"status": "started"}


@app.get("/api/pipeline/status")
async def pipeline_status():
    return {"is_running": _is_running}


@app.get("/api/pipeline/checkpoint")
async def get_checkpoint():
    summary = cp.summary()
    if not summary:
        return {"exists": False}
    return {"exists": True, **summary}


@app.post("/api/pipeline/resume")
async def resume_pipeline(background_tasks: BackgroundTasks):
    global _is_running
    if _is_running:
        raise HTTPException(status_code=409, detail="Pipeline already in progress")
    if not cp.exists():
        raise HTTPException(status_code=404, detail="No checkpoint found. Run the pipeline first.")
    missing = validate_config()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing env vars: {', '.join(missing)}")
    if not service_account_path().exists():
        raise HTTPException(status_code=400, detail="service_account.json not found in backend/ folder")
    _is_running = True
    _event_history.clear()

    async def _resume_wrapper():
        await _pipeline_run_core(resume_pipeline_async)

    background_tasks.add_task(_resume_wrapper)
    return {"status": "resuming"}


@app.delete("/api/pipeline/checkpoint")
async def delete_checkpoint():
    cp.clear()
    return {"status": "cleared"}


# ── History endpoints ─────────────────────────────────────────────────────────
@app.get("/api/history")
async def get_history():
    return run_history.get_all()


# ── Brevo stats endpoint ──────────────────────────────────────────────────────
@app.get("/api/brevo/stats")
async def get_brevo_stats(date: str = None):
    from config import BREVO_API_KEY
    if not BREVO_API_KEY:
        raise HTTPException(status_code=400, detail="Brevo API key not configured")
    target_date = date or dt_date.today().isoformat()
    headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
    try:
        r = await asyncio.to_thread(
            lambda: req.get(
                "https://api.brevo.com/v3/smtp/statistics/aggregatedReport",
                params={"startDate": target_date, "endDate": target_date},
                headers=headers,
                timeout=10,
            )
        )
        if r.ok:
            return r.json()
        return {"error": f"Brevo returned {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)[:200]}


# ── Automation next-runs endpoint ─────────────────────────────────────────────
@app.get("/api/automation/next-runs")
async def get_next_runs():
    return {"next_runs": sched.next_run_times()}


# ── Templates endpoints ───────────────────────────────────────────────────────
TEMPLATES_FILE = Path(__file__).parent.parent / "templates.json"


def _default_templates() -> dict:
    from templates import growth, branding, creative, social_media, generic, marketplace
    return {
        "Growth": {"subject": growth.SUBJECT, "body": growth.BODY},
        "Branding": {"subject": branding.SUBJECT, "body": branding.BODY},
        "Creative & Campaign": {"subject": creative.SUBJECT, "body": creative.BODY},
        "Social Media": {"subject": social_media.SUBJECT, "body": social_media.BODY},
        "Marketplace": {"subject": marketplace.SUBJECT, "body": marketplace.BODY},
        "Generic": {"subject": generic.SUBJECT, "body": generic.BODY},
    }


def _get_templates() -> dict:
    if TEMPLATES_FILE.exists():
        try:
            return json.loads(TEMPLATES_FILE.read_text())
        except Exception:
            pass
    return _default_templates()


@app.get("/api/templates")
async def get_templates():
    return _get_templates()


@app.post("/api/templates")
async def save_templates(request: Request):
    body = await request.json()
    TEMPLATES_FILE.write_text(json.dumps(body, indent=2))
    return {"status": "saved"}


# ── Admin config endpoints ────────────────────────────────────────────────────
@app.get("/api/admin/config")
async def get_admin_config():
    return admin_cfg.load()


@app.post("/api/admin/config")
async def save_admin_config(request: Request):
    body = await request.json()
    from admin_config import _deep_merge, DEFAULT_CONFIG
    merged = _deep_merge(DEFAULT_CONFIG, body)
    admin_cfg.save(merged)
    # Update scheduler with new automation config
    sched.update(merged.get("automation", {}))
    log.info("Admin config saved")
    return {"status": "saved"}


# ── Test email endpoint ───────────────────────────────────────────────────────
@app.post("/api/test-email")
async def send_test_email(request: Request):
    body = await request.json()
    to_email = (body.get("email") or "").strip()
    category = body.get("category") or "Generic"
    first_name = body.get("first_name") or "Rahul"
    company = body.get("company") or "BeautyBrand"
    post_snippet = body.get("post_snippet") or "Looking for a marketing agency to help scale our D2C brand"

    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    templates = _get_templates()
    tmpl = templates.get(category) or templates.get("Generic") or {}
    if not tmpl:
        raise HTTPException(status_code=400, detail=f"Template for category '{category}' not found")

    def _personalise(s: str) -> str:
        return (s
                .replace("{{first_name}}", first_name)
                .replace("{{company}}", company)
                .replace("{{post_snippet}}", post_snippet))

    subject = _personalise(tmpl.get("subject", "Test Email — Decision Pinnacle"))
    email_body = _personalise(tmpl.get("body", ""))

    from stages.brevo_sender import _send_one_sync_with_reply
    try:
        cfg = admin_cfg.load()
        reply_to = cfg.get("sending", {}).get("reply_to_email", "")
        await asyncio.to_thread(_send_one_sync_with_reply, to_email, first_name, subject, email_body, reply_to)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    log.info(f"Test email sent to {to_email} | category={category}")
    return {"status": "sent", "to": to_email, "subject": subject}


# ── Apollo plan check ────────────────────────────────────────────────────────
@app.get("/api/apollo/plan-check")
async def apollo_plan_check():
    from config import APOLLO_API_KEY
    if not APOLLO_API_KEY or APOLLO_API_KEY.startswith("your_"):
        return {"accessible": False, "reason": "No Apollo API key configured"}
    try:
        headers = {"X-Api-Key": APOLLO_API_KEY, "Content-Type": "application/json"}
        r = await asyncio.to_thread(
            lambda: req.post(
                "https://api.apollo.io/api/v1/people/bulk_match",
                json={"details": [{"linkedin_url": "https://www.linkedin.com/in/test"}]},
                headers=headers,
                timeout=10,
            )
        )
        if r.status_code == 200:
            return {"accessible": True, "reason": "Email enrichment is available"}
        if r.status_code == 403:
            return {
                "accessible": False,
                "reason": "Apollo free plan — email enrichment not included",
                "upgrade_url": "https://app.apollo.io/settings/plans",
            }
        return {"accessible": False, "reason": f"Apollo returned {r.status_code}"}
    except Exception as e:
        return {"accessible": False, "reason": str(e)[:100]}


# ── Config check endpoint ─────────────────────────────────────────────────────
@app.get("/api/config/check")
async def check_config():
    missing = validate_config()
    sa_exists = service_account_path().exists()
    return {
        "missing_vars": missing,
        "service_account_exists": sa_exists,
        "ready": len(missing) == 0 and sa_exists,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}",
    }


# ── Serve React frontend (production build) ───────────────────────────────────
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException as StarletteHTTPException

    class _SPAStaticFiles(StaticFiles):
        """StaticFiles that never intercepts /api/* paths.

        When a request targets an /api/ route that doesn't exist as a file,
        raise a 404 so FastAPI's JSON error handler responds instead of
        serving index.html.
        """

        async def get_response(self, path: str, scope):
            if path.startswith("api/") or path == "api":
                raise StarletteHTTPException(status_code=404)
            return await super().get_response(path, scope)

    app.mount("/", _SPAStaticFiles(directory=str(_frontend_dist), html=True), name="static")
