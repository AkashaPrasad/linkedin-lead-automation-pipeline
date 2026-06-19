import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "admin_config.json"

_DEFAULT_QUERIES = [
    "marketing agency",
    "digital agency",
    "media agency",
    "looking for agency",
    "need a marketing partner",
    "brand agency India",
    "performance marketing agency",
    "social media agency",
    "D2C marketing",
    "growth agency",
]

DEFAULT_CONFIG = {
    "scraping": {
        "search_queries": list(_DEFAULT_QUERIES),
        # Named, saved sets of search queries — lets you build up several keyword
        # lists (e.g. "search-1", "search-2") and switch which one is active
        # without retyping. "search_queries" above is always the currently active list.
        "query_sets": {"search-1": list(_DEFAULT_QUERIES)},
        "active_query_set": "search-1",
        "max_posts_per_query": 50,
        "total_post_cap": 500,
        "posted_limit": "month",
        "sort_by": "date",
        "author_industry_ids": [],
        "author_geo_ids": [],
        "min_post_length": 50,
    },
    "filtering": {
        "gpt_filter_enabled": True,
        "excluded_keywords": [],
        "only_posts_with_email": False,
        "language": "any",
    },
    "enrichment": {
        "apollo_enabled": True,
        "max_enrichment_per_run": 100,
    },
    "sending": {
        "daily_email_cap": 100,
        "email_send_delay_seconds": 2,
        "dry_run_mode": False,
        "excluded_domains": [],
        "reply_to_email": "",
    },
    "automation": {
        "enabled": False,
        "days": ["monday", "wednesday", "friday"],
        "times": ["09:00"],
        "timezone": "Asia/Kolkata",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            merged = _deep_merge(DEFAULT_CONFIG, data)
            # One-time migration: older configs saved before query_sets existed only
            # have a flat search_queries list — fold it into a "search-1" set so it's
            # not lost, then persist so this only runs once.
            if "query_sets" not in (data.get("scraping") or {}):
                scraping = merged.get("scraping", {})
                scraping["query_sets"] = {"search-1": list(scraping.get("search_queries") or [])}
                scraping["active_query_set"] = "search-1"
                merged["scraping"] = scraping
                save(merged)
            return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
