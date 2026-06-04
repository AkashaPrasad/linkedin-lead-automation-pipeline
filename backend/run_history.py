import json
import uuid
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent.parent / "run_history.json"


def _load() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def append_run(data: dict) -> str:
    runs = _load()
    run_id = str(uuid.uuid4())[:8]
    entry = {"id": run_id, "timestamp": datetime.now().isoformat(), **data}
    runs.insert(0, entry)
    HISTORY_FILE.write_text(json.dumps(runs[:100], indent=2))
    return run_id


def get_all() -> list:
    return _load()
