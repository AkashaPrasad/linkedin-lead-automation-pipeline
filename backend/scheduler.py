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
    global _scheduler, _run_fn
    _run_fn = run_fn
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    _scheduler.start()
    log.info("Scheduler started")


def update(automation_cfg: dict):
    if _scheduler is None:
        return
    _scheduler.remove_all_jobs()
    if not automation_cfg.get("enabled"):
        log.info("Automation disabled — no jobs scheduled")
        return

    days = automation_cfg.get("days", [])
    times = automation_cfg.get("times", ["09:00"])
    tz = automation_cfg.get("timezone", "Asia/Kolkata")
    day_str = ",".join(_DAY_MAP.get(d.lower(), d) for d in days) if days else "*"

    for t in times:
        try:
            h, m = t.split(":")
            _scheduler.add_job(
                _run_fn,
                CronTrigger(day_of_week=day_str, hour=int(h), minute=int(m), timezone=tz),
                misfire_grace_time=300,
                coalesce=True,
                id=f"pipeline_{t}_{day_str}",
                replace_existing=True,
            )
            log.info(f"Scheduled: {day_str} at {t} ({tz})")
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
