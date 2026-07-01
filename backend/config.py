import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "harvestapi~linkedin-post-search")
APIFY_COOKIE_ACTOR_ID = os.getenv("APIFY_COOKIE_ACTOR_ID", "curious_coder/linkedin-post-search-scraper")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Decision Pinnacle")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MAX_EMAILS_PER_RUN = int(os.getenv("MAX_EMAILS_PER_RUN", "100"))
APIFY_MAX_POSTS = int(os.getenv("APIFY_MAX_POSTS", "500"))
DAILY_EMAIL_CAP = int(os.getenv("DAILY_EMAIL_CAP", "100"))

_REQUIRED = [
    ("APIFY_API_TOKEN", APIFY_API_TOKEN),
    ("BREVO_API_KEY", BREVO_API_KEY),
    ("BREVO_SENDER_EMAIL", BREVO_SENDER_EMAIL),
    ("GOOGLE_SHEET_ID", GOOGLE_SHEET_ID),
    ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
    ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
]

def _is_placeholder(val: str) -> bool:
    return not val or val.startswith("your_")

def validate_config() -> list[str]:
    missing = [name for name, val in _REQUIRED if _is_placeholder(val)]
    openai_ok = not _is_placeholder(OPENAI_API_KEY)
    gemini_ok = not _is_placeholder(GEMINI_API_KEY)
    if not openai_ok and not gemini_ok:
        missing.append("OPENAI_API_KEY or GEMINI_API_KEY (at least one required)")
    return missing

def has_openai() -> bool:
    return not _is_placeholder(OPENAI_API_KEY)

def has_gemini() -> bool:
    return not _is_placeholder(GEMINI_API_KEY)

def get_linkedin_cookie() -> str:
    """Reads fresh from disk each call (not cached) so a UI-driven update
    takes effect on the next pipeline run without a restart.

    Previously this was stored in .env, which is gitignored and never part
    of the Docker image — every redeploy started a fresh container with no
    .env file at all, silently wiping the cookie regardless of any mounted
    volume. Now it lives under persistent_data_path, same as
    admin_config.json/templates.json, so it actually survives redeploys
    once CONFIG_DIR points at a mounted volume."""
    path = persistent_data_path("linkedin_cookie.json")
    if path.exists():
        return path.read_text().strip()
    # Fallback for local dev / anyone setting it directly as an env var
    return os.getenv("LINKEDIN_COOKIE", "")


def set_linkedin_cookie(value: str) -> None:
    """Persists the cookie under persistent_data_path so it survives
    redeploys once CONFIG_DIR is configured."""
    path = persistent_data_path("linkedin_cookie.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    os.environ["LINKEDIN_COOKIE"] = value


def service_account_path() -> Path:
    # On Railway/cloud, the JSON is injected as an env var to avoid committing secrets
    sa_json = os.getenv("SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        tmp = Path("/tmp/service_account.json")
        if not tmp.exists():
            tmp.write_text(sa_json)
        return tmp
    return Path(__file__).parent / GOOGLE_SERVICE_ACCOUNT_FILE


def persistent_data_path(filename: str) -> Path:
    """Path for a user-editable data file (admin_config.json, templates.json)
    that must survive redeploys.

    Without this, these files are baked into the Docker image from git at
    build time — every redeploy starts a fresh container from that image,
    silently discarding anything saved through the UI since the last commit
    (new query sets, scraping settings, template edits, etc).

    If CONFIG_DIR is set (a Railway Volume — or equivalent persistent disk
    on another host — mounted at that path), the file lives there instead
    and is seeded once from the repo's bundled version on first boot. After
    that, redeploys never touch it again — only an explicit git change to
    the bundled file affects it, and only for brand-new deployments that
    haven't seeded yet.

    Without CONFIG_DIR (e.g. local dev), falls back to the repo root so
    local behavior is unchanged.
    """
    config_dir = os.getenv("CONFIG_DIR", "")
    if not config_dir:
        return Path(__file__).parent.parent / filename
    persistent_path = Path(config_dir) / filename
    if not persistent_path.exists():
        bundled = Path(__file__).parent.parent / filename
        persistent_path.parent.mkdir(parents=True, exist_ok=True)
        if bundled.exists():
            import shutil
            shutil.copy(bundled, persistent_path)
    return persistent_path


def persistent_dir(name: str) -> Path:
    """Directory for generated data (e.g. per-run logs) that has no bundled
    default and must still survive redeploys. Same CONFIG_DIR mechanism as
    persistent_data_path, just for a directory instead of a single seeded
    file."""
    config_dir = os.getenv("CONFIG_DIR", "")
    base = Path(config_dir) if config_dir else Path(__file__).parent.parent
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d
