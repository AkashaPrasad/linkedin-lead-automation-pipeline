"""
Pipeline checkpoint — saves state after key stages so the pipeline can
resume from where it stopped without re-running expensive Apify/AI stages.

Checkpoint is saved after Stage 4 (AI Classify) and Stage 5 (Sheets Write).
On the next run the user can choose to resume instead of starting fresh.
"""
import json
from pathlib import Path
from config import now_ist
from logger import get_logger

log = get_logger("checkpoint")

CHECKPOINT_FILE = Path(__file__).parent.parent / "pipeline_checkpoint.json"


def save(stage_completed: int, data: dict) -> None:
    state = {
        "stage_completed": stage_completed,
        "timestamp": now_ist().isoformat(),
        **data,
    }
    try:
        CHECKPOINT_FILE.write_text(json.dumps(state, default=str, indent=2))
        log.info(f"Checkpoint saved after Stage {stage_completed}")
    except Exception as e:
        log.warning(f"Could not save checkpoint: {e}")


def load() -> dict | None:
    if not CHECKPOINT_FILE.exists():
        return None
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except Exception as e:
        log.warning(f"Could not load checkpoint: {e}")
        return None


def clear() -> None:
    try:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
            log.info("Checkpoint cleared")
    except Exception:
        pass


def exists() -> bool:
    return CHECKPOINT_FILE.exists()


def summary() -> dict | None:
    cp = load()
    if not cp:
        return None
    return {
        "stage_completed": cp.get("stage_completed"),
        "timestamp": cp.get("timestamp"),
        "stats": cp.get("stats", {}),
        "dry_run": cp.get("dry_run", False),
        "daily_tab": cp.get("daily_tab", ""),
        "real_posts_count": len(cp.get("real_posts", [])),
    }
