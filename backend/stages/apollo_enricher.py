import asyncio
import requests
from logger import get_logger

log = get_logger("apollo")

APOLLO_BULK_URL = "https://api.apollo.io/api/v1/people/bulk_match"


def _get_headers() -> dict:
    from config import APOLLO_API_KEY
    return {"X-Api-Key": APOLLO_API_KEY, "Content-Type": "application/json"}


def _bulk_match_sync(linkedin_urls: list[str]) -> list[str | None]:
    payload = {
        "reveal_personal_emails": True,
        "details": [{"linkedin_url": url} for url in linkedin_urls],
    }
    resp = requests.post(APOLLO_BULK_URL, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code == 401:
        raise PermissionError("Apollo API key is invalid or expired")

    if resp.status_code == 403:
        try:
            msg = resp.json().get("error", "")
        except Exception:
            msg = resp.text[:200]
        if "free plan" in msg.lower() or "inaccessible" in msg.lower():
            raise PermissionError(
                "Apollo plan does not include email enrichment. "
                "Upgrade to Apollo Starter ($49/mo) at https://app.apollo.io/settings/plans "
                "to enable this feature. Until then, only emails found directly in LinkedIn posts will be used."
            )
        raise PermissionError(f"Apollo access denied: {msg}")

    if resp.status_code == 429:
        raise ConnectionError("Apollo rate limit hit")

    resp.raise_for_status()
    data = resp.json()
    matches = data.get("matches") or []
    emails = []
    for match in matches:
        try:
            email = match.get("email") if isinstance(match, dict) else None
            emails.append(email if email and "@" in email else None)
        except Exception:
            emails.append(None)

    while len(emails) < len(linkedin_urls):
        emails.append(None)
    return emails


async def run_apollo_enricher(real_posts: list[dict], master_ws, daily_ws, emit, max_enrichment: int = 100) -> list[dict]:
    await emit({"event": "stage_start", "stage": 6, "name": "Apollo Enrichment",
                "message": "Enriching missing emails via Apollo..."})

    from post_fields import get_author_url
    needs_enrichment = [
        (i, p) for i, p in enumerate(real_posts)
        if not p.get("_email_in_post") and p.get("_lead_status", "REAL") == "REAL"
        and get_author_url(p)
    ][:max_enrichment]

    if not needs_enrichment:
        await emit({
            "event": "stage_complete",
            "stage": 6,
            "name": "Apollo Enrichment",
            "metric": "No posts needed enrichment",
            "enriched": 0,
            "not_found": 0,
        })
        return real_posts

    enriched_count = 0
    not_found_count = 0
    plan_blocked = False

    batch_size = 10
    batches = [needs_enrichment[i:i + batch_size] for i in range(0, len(needs_enrichment), batch_size)]

    for batch in batches:
        if plan_blocked:
            break

        urls = [get_author_url(p) for _, p in batch]
        emails = None

        for attempt in range(2):
            try:
                emails = await asyncio.to_thread(_bulk_match_sync, urls)
                break
            except PermissionError as e:
                err_msg = str(e)
                log.error(f"Apollo blocked: {err_msg}")
                await emit({"event": "log", "level": "WARN",
                            "message": f"⚠ Apollo enrichment skipped — {err_msg}"})
                plan_blocked = True
                emails = [None] * len(urls)
                break
            except ConnectionError:
                if attempt == 0:
                    log.warning("Apollo rate limit — waiting 30s...")
                    await emit({"event": "progress", "stage": 6,
                                "message": "Apollo rate limit — waiting 30 seconds..."})
                    await asyncio.sleep(30)
                else:
                    log.error("Apollo rate limit on retry — skipping batch")
                    emails = [None] * len(urls)
            except Exception as e:
                log.error(f"Apollo error: {e}")
                emails = [None] * len(urls)
                break

        if emails is None:
            emails = [None] * len(urls)

        for (orig_idx, post), email in zip(batch, emails):
            post["_apollo_email"] = email or None
            if email:
                enriched_count += 1
            else:
                not_found_count += 1

        if not plan_blocked:
            await emit({
                "event": "progress",
                "stage": 6,
                "message": f"Apollo: enriched {enriched_count}, not found {not_found_count}",
            })

    metric = f"{enriched_count} emails enriched"
    if plan_blocked:
        metric = "Skipped — Apollo paid plan required for email enrichment"

    await emit({
        "event": "stage_complete",
        "stage": 6,
        "name": "Apollo Enrichment",
        "metric": metric,
        "enriched": enriched_count,
        "not_found": not_found_count,
    })
    log.info(f"STAGE 6 | Apollo: {enriched_count} enriched, {not_found_count} not found, blocked={plan_blocked}")
    return real_posts
