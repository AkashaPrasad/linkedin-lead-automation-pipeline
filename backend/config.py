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

_ENV_FILE = Path(__file__).parent.parent / ".env"


def get_linkedin_cookie() -> str:
    """Reads live from the environment (not a cached module constant) so a
    UI-driven update takes effect on the next pipeline run without a restart."""
    return os.getenv("LINKEDIN_COOKIE", "")


def set_linkedin_cookie(value: str) -> None:
    """Updates the cookie for the running process and persists it to .env
    (gitignored) so it survives a restart."""
    os.environ["LINKEDIN_COOKIE"] = value
    lines = _ENV_FILE.read_text().splitlines() if _ENV_FILE.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith("LINKEDIN_COOKIE="):
            lines[i] = f"LINKEDIN_COOKIE={value}"
            found = True
            break
    if not found:
        lines.append(f"LINKEDIN_COOKIE={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


def service_account_path() -> Path:
    # On Railway/cloud, the JSON is injected as an env var to avoid committing secrets
    sa_json = os.getenv("SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        tmp = Path("/tmp/service_account.json")
        if not tmp.exists():
            tmp.write_text(sa_json)
        return tmp
    return Path(__file__).parent / GOOGLE_SERVICE_ACCOUNT_FILE
