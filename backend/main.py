import asyncio
import json
import sys
from datetime import date as dt_date
from pathlib import Path
from collections import deque
from contextlib import asynccontextmanager

import requests as req
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from config import validate_config, GOOGLE_SHEET_ID, service_account_path, persistent_data_path
from logger import get_logger
from pipeline import run_pipeline_async, resume_pipeline_async
from stages.alerts import send_alert
import admin_config as admin_cfg
import checkpoint as cp
import run_history
import scheduler as sched

log = get_logger("main")

# ── SSE state ────────────────────────────────────────────────────────────────
_subscribers: list[asyncio.Queue] = []
_event_history: deque = deque(maxlen=500)
_is_running = False
_current_task: asyncio.Task | None = None


async def broadcast(event: dict):
    _event_history.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def _pipeline_run_core(wrapper_fn):
    """Runs the pipeline, captures the FULL event transcript + history,
    resets _is_running. Every run is recorded — completed, failed, or
    stopped — with its complete log, not just successful ones, so a crash
    or manual stop can actually be investigated afterward via History."""
    global _is_running
    last_stats: dict = {}
    complete_data: dict | None = None
    error_data: dict | None = None
    stopped_data: dict | None = None
    full_log: list[dict] = []

    async def _capturing_emit(event: dict):
        nonlocal complete_data, error_data, stopped_data
        full_log.append(event)
        await broadcast(event)
        ev = event.get("event")
        if ev == "stats":
            last_stats.update(event)
        elif ev == "complete":
            complete_data = event
        elif ev == "error":
            error_data = event
        elif ev == "stopped":
            stopped_data = event

    exc_message: str | None = None
    try:
        await wrapper_fn(_capturing_emit)
    except Exception as e:
        # Not every failure path emits an "error" SSE event (e.g. promote
        # raising RuntimeError before any event fires) — without this, such
        # a run would be recorded as "unknown" with no indication of what
        # went wrong. Capture it here, then re-raise so existing callers
        # (background task logging, _scheduled_pipeline_run's own handler)
        # behave exactly as before.
        exc_message = str(e)
        raise
    finally:
        _is_running = False

        if complete_data:
            summary = {
                "status": "completed",
                "scraped": complete_data.get("scraped", 0),
                "real": complete_data.get("real", 0),
                "enriched": last_stats.get("enriched", 0),
                "with_email": complete_data.get("with_email", 0),
                "sent": complete_data.get("sent", 0),
                "failed": complete_data.get("failed", 0),
                "no_email": complete_data.get("no_email", 0),
                "duration_min": complete_data.get("duration_min", 0),
                "dry_run": complete_data.get("dry_run", False),
            }
        elif error_data:
            summary = {
                "status": "failed",
                "scraped": last_stats.get("scraped", 0),
                "real": last_stats.get("real", 0),
                "enriched": last_stats.get("enriched", 0),
                "with_email": 0,
                "sent": last_stats.get("sent", 0),
                "failed": 0,
                "no_email": 0,
                "duration_min": 0,
                "dry_run": False,
                "error_message": error_data.get("message", ""),
            }
        elif stopped_data:
            summary = {
                "status": "stopped",
                "scraped": last_stats.get("scraped", 0),
                "real": last_stats.get("real", 0),
                "enriched": last_stats.get("enriched", 0),
                "with_email": 0,
                "sent": last_stats.get("sent", 0),
                "failed": 0,
                "no_email": 0,
                "duration_min": 0,
                "dry_run": False,
            }
        elif exc_message:
            summary = {
                "status": "failed",
                "scraped": last_stats.get("scraped", 0),
                "real": last_stats.get("real", 0),
                "enriched": last_stats.get("enriched", 0),
                "with_email": 0,
                "sent": last_stats.get("sent", 0),
                "failed": 0,
                "no_email": 0,
                "duration_min": 0,
                "dry_run": False,
                "error_message": exc_message,
            }
        else:
            # Crashed before emitting anything at all (e.g. failed to even
            # reach Stage 1) — still record it so it's not invisible.
            summary = {
                "status": "unknown", "scraped": 0, "real": 0, "enriched": 0,
                "with_email": 0, "sent": 0, "failed": 0, "no_email": 0,
                "duration_min": 0, "dry_run": False,
            }

        summary["date"] = dt_date.today().isoformat()
        run_history.append_run(summary, full_log)


async def _pipeline_wrapper():
    await _pipeline_run_core(run_pipeline_async)


# A hung/runaway automated run must never block forever — APScheduler shares
# the same event loop as the rest of the app, so an unbounded scheduled job
# is a real risk to overall uptime, not just to that one run. 3 hours is
# generous for the heaviest realistic workload but still a hard ceiling.
AUTOMATION_TIMEOUT_SECONDS = 3 * 60 * 60


async def _scheduled_pipeline_run():
    global _is_running, _current_task

    if _is_running:
        log.warning("Scheduled run skipped — pipeline already running")
        await send_alert("⏭ Scheduled run skipped — a pipeline run was already in progress")
        return

    # Manual runs validate config before starting; the scheduled path
    # previously skipped this and could fail deep into a multi-stage run
    # with no one watching. Fail fast instead.
    missing = validate_config()
    if missing:
        log.error(f"Scheduled run aborted — missing env vars: {', '.join(missing)}")
        await send_alert(f"❌ Scheduled run aborted — missing env vars: {', '.join(missing)}")
        return
    if not service_account_path().exists():
        log.error("Scheduled run aborted — service_account.json not found")
        await send_alert("❌ Scheduled run aborted — service_account.json not found in backend/ folder")
        return

    cfg = admin_cfg.load()
    if cfg.get("scraping", {}).get("use_cookie_actor"):
        from config import get_linkedin_cookie
        cookie_ok = False
        cookie_raw = get_linkedin_cookie()
        if cookie_raw:
            try:
                parsed = json.loads(cookie_raw)
                cookie_ok = isinstance(parsed, list) and len(parsed) > 0
            except Exception:
                cookie_ok = False
        if not cookie_ok:
            log.error("Scheduled run aborted — cookie scraping enabled but LINKEDIN_COOKIE missing/invalid")
            await send_alert(
                "❌ Scheduled run aborted — cookie scraping is on but the LinkedIn cookie is "
                "missing or invalid. Update it in Admin Panel, or turn off cookie mode."
            )
            return

    _is_running = True
    _event_history.clear()
    log.info("Scheduled pipeline run starting")
    await send_alert("⏰ Scheduled pipeline run starting")

    try:
        _current_task = asyncio.create_task(_pipeline_run_core(run_pipeline_async))
        await asyncio.wait_for(_current_task, timeout=AUTOMATION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.error(f"Scheduled run exceeded {AUTOMATION_TIMEOUT_SECONDS}s — cancelling")
        if _current_task:
            _current_task.cancel()
        await send_alert(
            f"🛑 Scheduled run timed out after {AUTOMATION_TIMEOUT_SECONDS // 3600}h and was cancelled automatically"
        )
    except Exception as e:
        log.error(f"Scheduled run crashed: {e}", exc_info=True)
        await send_alert(f"❌ Scheduled run crashed: {str(e)[:200]}")
    finally:
        # Belt-and-suspenders — _pipeline_run_core already resets _is_running
        # in its own finally, but a hard guarantee here means a stuck flag
        # (and the "already running forever" lockup that causes) is no
        # longer possible no matter what goes wrong above.
        _is_running = False
        _current_task = None


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
async def run_pipeline():
    global _is_running, _current_task
    if _is_running:
        raise HTTPException(status_code=409, detail="Pipeline already in progress")
    missing = validate_config()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing env vars: {', '.join(missing)}")
    if not service_account_path().exists():
        raise HTTPException(status_code=400, detail="service_account.json not found in backend/ folder")
    _is_running = True
    _event_history.clear()
    _current_task = asyncio.create_task(_pipeline_wrapper())
    return {"status": "started"}


@app.get("/api/pipeline/status")
async def pipeline_status():
    return {"is_running": _is_running}


@app.post("/api/pipeline/stop")
async def stop_pipeline():
    global _is_running, _current_task
    if not _is_running:
        raise HTTPException(status_code=400, detail="No pipeline is currently running")
    if _current_task is not None:
        _current_task.cancel()
        _current_task = None
    _is_running = False
    await broadcast({"event": "stopped", "message": "Pipeline stopped by user"})
    await send_alert("🛑 Pipeline stopped manually")
    log.info("Pipeline stopped manually via /api/pipeline/stop")
    return {"status": "stopped"}


@app.get("/api/pipeline/checkpoint")
async def get_checkpoint():
    summary = cp.summary()
    if not summary:
        return {"exists": False}
    return {"exists": True, **summary}


@app.post("/api/pipeline/resume")
async def resume_pipeline():
    global _is_running, _current_task
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

    _current_task = asyncio.create_task(_resume_wrapper())
    return {"status": "resuming"}


@app.delete("/api/pipeline/checkpoint")
async def delete_checkpoint():
    cp.clear()
    return {"status": "cleared"}


# ── Promote dry run to real send ──────────────────────────────────────────────
@app.get("/api/pipeline/promote/tabs")
async def list_dry_run_tabs():
    """Lists sheet tabs that look like dry-run tabs (titled '[DRY] <date>'),
    so the UI can offer a picker instead of requiring the exact tab name."""
    from stages.sheets_writer import open_sheets
    try:
        sh = await open_sheets()
        titles = await asyncio.to_thread(lambda: [ws.title for ws in sh.worksheets()])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read sheet tabs: {e}")
    dry_tabs = [t for t in titles if t.startswith("[DRY]")]
    return {"tabs": dry_tabs}


@app.get("/api/pipeline/promote/preview")
async def promote_preview(tab: str):
    """Read-only — counts how many rows in the given tab qualify for
    promotion, without writing or sending anything."""
    from promote import count_promotable_sync
    try:
        result = await asyncio.to_thread(count_promotable_sync, tab)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not read tab '{tab}': {e}")
    return result


@app.post("/api/pipeline/promote")
async def promote_dry_run(request: Request):
    global _is_running, _current_task
    if _is_running:
        raise HTTPException(status_code=409, detail="Pipeline already in progress")
    body = await request.json()
    tab_name = (body.get("tab_name") or "").strip()
    if not tab_name:
        raise HTTPException(status_code=400, detail="tab_name required")
    missing = validate_config()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing env vars: {', '.join(missing)}")
    if not service_account_path().exists():
        raise HTTPException(status_code=400, detail="service_account.json not found in backend/ folder")
    _is_running = True
    _event_history.clear()

    async def _promote_wrapper():
        from promote import promote_dry_run_async
        await _pipeline_run_core(lambda emit: promote_dry_run_async(emit, tab_name))

    _current_task = asyncio.create_task(_promote_wrapper())
    return {"status": "started", "tab_name": tab_name}


# ── History endpoints ─────────────────────────────────────────────────────────
@app.get("/api/history")
async def get_history():
    return run_history.get_all()


@app.get("/api/history/{run_id}/logs")
async def get_history_logs(run_id: str):
    logs = run_history.get_log(run_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="No logs found for this run")
    return {"run_id": run_id, "events": logs}


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
TEMPLATES_FILE = persistent_data_path("templates.json")


def _default_templates() -> dict:
    from templates import generic
    return {
        "Generic": {"subject": generic.SUBJECT, "body": generic.BODY},
        "Growth": {"subject": "", "body": ""},
        "Production": {"subject": "", "body": ""},
        "Influencer Marketing": {"subject": "", "body": ""},
        "Branding": {"subject": "", "body": ""},
        "Creative": {"subject": "", "body": ""},
        "Creative - FMCG": {"subject": "", "body": ""},
        "Creative - Real Estate": {"subject": "", "body": ""},
        "Creative - Apparel": {"subject": "", "body": ""},
        "Creative - Kids": {"subject": "", "body": ""},
        "Creative - Beauty": {"subject": "", "body": ""},
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
    tmpl = templates.get(category) or {}
    generic_tmpl = templates.get("Generic") or {}
    if not tmpl and not generic_tmpl:
        raise HTTPException(status_code=400, detail=f"Template for category '{category}' not found")

    def _personalise(s: str) -> str:
        return (s
                .replace("{{first_name}}", first_name)
                .replace("{{company}}", company)
                .replace("{{post_snippet}}", post_snippet))

    # Fall back to Generic per-field, not per-category — a category can
    # exist with a blank subject/body (not yet written), which would
    # otherwise be sent to Brevo as-is and rejected with a 400.
    subject_raw = tmpl.get("subject") or generic_tmpl.get("subject") or "Test Email — Decision Pinnacle"
    body_raw = tmpl.get("body") or generic_tmpl.get("body") or ""
    subject = _personalise(subject_raw)
    email_body = _personalise(body_raw)

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


# ── LinkedIn cookie endpoints ─────────────────────────────────────────────────
@app.get("/api/linkedin-cookie/status")
async def linkedin_cookie_status():
    from config import get_linkedin_cookie
    cookie = get_linkedin_cookie()
    try:
        count = len(json.loads(cookie)) if cookie else 0
    except Exception:
        count = 0
    return {"configured": count > 0, "preview": f"{count} cookies" if count else ""}


@app.post("/api/linkedin-cookie")
async def update_linkedin_cookie(request: Request):
    body = await request.json()
    value = (body.get("cookie") or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Cookie export required")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Not valid JSON — paste the full Cookie-Editor export")
    if not isinstance(parsed, list) or not parsed:
        raise HTTPException(status_code=400, detail="Must be a JSON array of cookie objects, not a single value")
    from config import set_linkedin_cookie
    set_linkedin_cookie(value)
    log.info(f"LinkedIn cookies updated via admin UI ({len(parsed)} cookies)")
    return {"status": "saved"}


# ── Apollo plan check ────────────────────────────────────────────────────────
@app.get("/api/apollo/plan-check")
async def apollo_plan_check():
    from config import APOLLO_API_KEY
    if not APOLLO_API_KEY or APOLLO_API_KEY.startswith("your_"):
        return {"accessible": False, "reason": "No Apollo API key configured"}
    headers = {"X-Api-Key": APOLLO_API_KEY, "Content-Type": "application/json"}
    # Mirror the real enrichment call exactly (same payload shape, including
    # reveal_personal_emails) so this check reflects what a live run will actually hit.
    payload = {
        "reveal_personal_emails": True,
        "details": [{"linkedin_url": "https://www.linkedin.com/in/test"}],
    }
    last_status = None
    last_body = ""
    for attempt in range(2):
        try:
            r = await asyncio.to_thread(
                lambda: req.post(
                    "https://api.apollo.io/api/v1/people/bulk_match",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
            )
        except Exception as e:
            return {"accessible": False, "reason": str(e)[:100]}

        if r.status_code == 200:
            return {"accessible": True, "reason": "Email enrichment is available"}
        if r.status_code == 401:
            return {"accessible": False, "reason": "Apollo API key is invalid or expired"}
        if r.status_code == 429 and attempt == 0:
            continue  # rate limited on first try — retry once before concluding anything
        last_status = r.status_code
        try:
            last_body = r.json().get("error", "") or r.text[:200]
        except Exception:
            last_body = r.text[:200]
        break

    if last_status == 403:
        # Only treat this as a real plan restriction if Apollo's own message says so —
        # a 403 can also come from this probe's throwaway test URL and isn't always plan-related.
        if "free plan" in last_body.lower() or "inaccessible" in last_body.lower():
            return {
                "accessible": False,
                "reason": "Apollo free plan — email enrichment not included",
                "upgrade_url": "https://app.apollo.io/settings/plans",
            }
        return {
            "accessible": False,
            "reason": f"Apollo access denied: {last_body or 'unknown reason'} "
                       "(this may be a key/permission issue rather than your plan tier — verify in Apollo settings)",
        }
    return {"accessible": False, "reason": f"Apollo returned {last_status}: {last_body}"[:200]}


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
