import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None
_run_fn = None

_DAY_MAP = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}


def init(run_fn):
    """Starts the scheduler. Defensive by design: this runs inside FastAPI's
    lifespan at startup with nothing catching exceptions above it — an
    unhandled error here (e.g. a missing IANA timezone database on a slim
    Docker image, which raises zoneinfo.ZoneInfoNotFoundError) would crash
    the ENTIRE app on boot, not just automation. requirements.txt now pins
    `tzdata` to prevent that at the source, but this try/except is a second
    layer: if scheduling ever fails for any reason, automation is simply
    disabled (logged clearly) instead of taking the whole site down."""
    global _scheduler, _run_fn
    _run_fn = run_fn
    try:
        _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        _scheduler.start()
        log.info("Scheduler started")
    except Exception as e:
        _scheduler = None
        log.error(f"Scheduler failed to start — automation will be unavailable: {e}", exc_info=True)


def update(automation_cfg: dict):
    """Called both at startup and every time admin config is saved — must
    never raise, or it would either crash startup (via lifespan) or break
    the /api/admin/config save endpoint for unrelated settings changes."""
    if _scheduler is None:
        return
    try:
        _scheduler.remove_all_jobs()
    except Exception as e:
        log.error(f"Failed to clear existing scheduled jobs: {e}")
        return

    if not automation_cfg.get("enabled"):
        log.info("Automation disabled — no jobs scheduled")
        return

    days = automation_cfg.get("days", [])
    times = automation_cfg.get("times", ["09:00"])
    time_query_sets = automation_cfg.get("time_query_sets", {})
    time_cookie_modes = automation_cfg.get("time_cookie_modes", {})
    tz = automation_cfg.get("timezone", "Asia/Kolkata")
    day_str = ",".join(_DAY_MAP.get(d.lower(), d) for d in days) if days else "*"

    for t in times:
        try:
            h, m = t.split(":")
            # None (not just "") means "no override" — run_pipeline_async
            # treats both "not passed" and None identically, falling back
            # to whatever query list / cookie setting is currently the default.
            query_set = time_query_sets.get(t) or None
            cookie_mode = time_cookie_modes.get(t) or None
            _scheduler.add_job(
                _run_fn,
                CronTrigger(day_of_week=day_str, hour=int(h), minute=int(m), timezone=tz),
                args=[query_set, cookie_mode],
                misfire_grace_time=300,
                coalesce=True,
                id=f"pipeline_{t}_{day_str}",
                replace_existing=True,
            )
            labels = []
            if query_set:
                labels.append(f"query folder '{query_set}'")
            if cookie_mode:
                labels.append(f"'{cookie_mode}' scraping")
            label = f" using {', '.join(labels)}" if labels else ""
            log.info(f"Scheduled: {day_str} at {t} ({tz}){label}")
        except Exception as e:
            log.error(f"Failed to schedule {t}: {e}")


def next_run_times() -> list[str]:
    if not _scheduler:
        return []
    result = []
    for job in _scheduler.get_jobs():
        nt = job.next_run_time
        if nt:
            result.append(nt.isoformat())
    return sorted(result)


def shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)
