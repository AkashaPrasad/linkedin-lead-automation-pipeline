import os
import random
import re
import threading
import time

AI_BATCH_SIZE = max(1, int(os.getenv("AI_BATCH_SIZE", "3")))
AI_MAX_RETRIES = max(1, int(os.getenv("AI_MAX_RETRIES", "3")))
AI_RETRY_BASE_SECONDS = max(0.1, float(os.getenv("AI_RETRY_BASE_SECONDS", "0.75")))
AI_RETRY_MAX_SECONDS = max(AI_RETRY_BASE_SECONDS, float(os.getenv("AI_RETRY_MAX_SECONDS", "8")))
AI_PROVIDER_ORDER = tuple(
    name.strip().lower()
    for name in os.getenv("AI_PROVIDER_ORDER", "gemini,openai").split(",")
    if name.strip()
)

_RETRY_AFTER_MS_RE = re.compile(r"try again in (\d+)ms", re.IGNORECASE)
_RETRY_AFTER_S_RE = re.compile(r"retry after (\d+(?:\.\d+)?)s", re.IGNORECASE)
_PROVIDER_COOLDOWNS: dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()
_TRANSIENT_MARKERS = (
    "rate limit",
    "429",
    "resource exhausted",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "service unavailable",
    "too many requests",
)


def provider_display_name(name: str) -> str:
    return {"openai": "OpenAI", "gemini": "Gemini"}.get(name.lower(), name)


def provider_order(available: list[str]) -> list[str]:
    ordered = []
    seen = set()

    for name in AI_PROVIDER_ORDER:
        if name in available and name not in seen:
            ordered.append(name)
            seen.add(name)

    for name in available:
        if name not in seen:
            ordered.append(name)
            seen.add(name)

    return ordered


def is_transient_ai_error(err: Exception) -> bool:
    status_code = getattr(err, "status_code", None)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True

    response = getattr(err, "response", None)
    if response is not None and getattr(response, "status_code", None) in {408, 409, 429, 500, 502, 503, 504}:
        return True

    text = str(err).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _retry_after_seconds(err: Exception, attempt: int) -> float:
    text = str(err)

    match = _RETRY_AFTER_MS_RE.search(text)
    if match:
        delay = max(int(match.group(1)) / 1000.0, AI_RETRY_BASE_SECONDS)
    else:
        match = _RETRY_AFTER_S_RE.search(text)
        if match:
            delay = max(float(match.group(1)), AI_RETRY_BASE_SECONDS)
        else:
            delay = AI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))

    jitter = random.uniform(0.05, 0.25)
    return min(delay + jitter, AI_RETRY_MAX_SECONDS)


def _wait_for_provider_slot(provider: str) -> None:
    with _COOLDOWN_LOCK:
        cooldown_until = _PROVIDER_COOLDOWNS.get(provider, 0.0)

    sleep_for = cooldown_until - time.monotonic()
    if sleep_for > 0:
        time.sleep(sleep_for)


def _set_provider_cooldown(provider: str, delay_seconds: float) -> None:
    cooldown_until = time.monotonic() + delay_seconds
    with _COOLDOWN_LOCK:
        current = _PROVIDER_COOLDOWNS.get(provider, 0.0)
        if cooldown_until > current:
            _PROVIDER_COOLDOWNS[provider] = cooldown_until


def call_with_retries(provider: str, func, log, action: str):
    last_err = None
    display_name = provider_display_name(provider)

    for attempt in range(1, AI_MAX_RETRIES + 1):
        _wait_for_provider_slot(provider)
        try:
            return func()
        except Exception as err:
            last_err = err
            if attempt >= AI_MAX_RETRIES or not is_transient_ai_error(err):
                raise

            delay = _retry_after_seconds(err, attempt)
            _set_provider_cooldown(provider, delay)
            log.warning(
                f"{display_name} {action} transient failure "
                f"(attempt {attempt}/{AI_MAX_RETRIES}); retrying in {delay:.2f}s: {err}"
            )

    raise last_err
