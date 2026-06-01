import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "admin_config.json"

DEFAULT_CONFIG = {
    "scraping": {
        "search_queries": [
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
        ],
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
            return _deep_merge(DEFAULT_CONFIG, data)
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
