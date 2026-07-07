import json
import uuid
from config import persistent_data_path, persistent_dir, now_ist

HISTORY_FILE = persistent_data_path("run_history.json")
RUN_LOGS_DIR = persistent_dir("run_logs")


def _load() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def _prune_orphaned_logs(current_runs: list[dict]) -> None:
    """Keeps run_logs/ in sync with the trimmed 100-run history — deletes
    log files for runs that fell off the list instead of growing forever."""
    valid_ids = {r["id"] for r in current_runs if "id" in r}
    try:
        for f in RUN_LOGS_DIR.glob("*.json"):
            if f.stem not in valid_ids:
                f.unlink()
    except Exception:
        pass


def append_run(data: dict, full_log: list[dict] | None = None) -> str:
    runs = _load()
    run_id = str(uuid.uuid4())[:8]
    # now_ist().isoformat() includes an explicit "+05:30" offset — this is
    # what lets the frontend's `new Date(...)` parse it correctly regardless
    # of the browser's own timezone, unlike a naive (offset-less) timestamp.
    entry = {"id": run_id, "timestamp": now_ist().isoformat(), **data}
    runs.insert(0, entry)
    runs = runs[:100]
    HISTORY_FILE.write_text(json.dumps(runs, indent=2))

    if full_log is not None:
        try:
            (RUN_LOGS_DIR / f"{run_id}.json").write_text(json.dumps(full_log, indent=2))
        except Exception:
            pass
        _prune_orphaned_logs(runs)

    return run_id


def get_all() -> list:
    return _load()


def get_log(run_id: str) -> list[dict] | None:
    log_path = RUN_LOGS_DIR / f"{run_id}.json"
    if not log_path.exists():
        return None
    try:
        return json.loads(log_path.read_text())
    except Exception:
        return None
