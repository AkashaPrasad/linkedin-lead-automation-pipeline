import asyncio
import re
import json
import requests
from datetime import datetime
from logger import get_logger
from config import DAILY_EMAIL_CAP, persistent_data_path

log = get_logger("brevo")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
# Must match main.py's TEMPLATES_FILE exactly (persistent_data_path, not a
# plain repo-root path) — otherwise, once CONFIG_DIR is set on a host like
# Railway, template edits made through the Admin UI get written to the
# persistent path while the actual send logic here would keep reading the
# stale bundled-in-the-image version, so edits would silently never apply.
TEMPLATES_FILE = persistent_data_path("templates.json")


def _get_headers() -> dict:
    """Build headers fresh each call so env-var changes take effect immediately."""
    from config import BREVO_API_KEY
    return {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}


def _get_sender() -> tuple[str, str]:
    from config import BREVO_SENDER_EMAIL, BREVO_SENDER_NAME
    return BREVO_SENDER_EMAIL, BREVO_SENDER_NAME


def _parse_brevo_error(resp: requests.Response) -> str:
    """Extract a useful message from a Brevo error response."""
    try:
        body = resp.json()
        msg = body.get("message", "")
        code = body.get("code", "")
        if code == "unauthorized" and "unrecognised IP" in msg:
            import re as _re
            ip_match = _re.search(r"address ([\da-fA-F:.]+)", msg)
            ip = ip_match.group(1) if ip_match else "your current IP"
            return (
                f"Brevo is blocking requests from {ip}. "
                f"To fix: go to https://app.brevo.com/security/authorised_ips and add {ip}, "
                f"OR remove all IP restrictions for development use."
            )
        if msg:
            return f"Brevo error ({resp.status_code}): {msg}"
    except Exception:
        pass
    return f"Brevo HTTP {resp.status_code}: {resp.text[:200]}"


def _check_resp(resp: requests.Response) -> None:
    if resp.ok:
        return
    err = _parse_brevo_error(resp)
    if resp.status_code == 401:
        raise PermissionError(err)
    if resp.status_code == 402:
        raise OverflowError("Brevo daily send limit reached")
    if resp.status_code == 429:
        raise ConnectionError("Brevo rate limit — too many requests")
    if resp.status_code == 400:
        raise ValueError(err)
    raise RuntimeError(err)


def _load_templates() -> dict:
    if TEMPLATES_FILE.exists():
        try:
            return json.loads(TEMPLATES_FILE.read_text())
        except Exception:
            pass
    from templates import generic
    return {"Generic": {"subject": generic.SUBJECT, "body": generic.BODY}}


def _extract_company(headline: str) -> str:
    for sep in [" at ", " @ ", " | ", " - "]:
        if sep.lower() in headline.lower():
            idx = headline.lower().find(sep.lower())
            return headline[idx + len(sep):].strip()
    return headline.strip() or "your company"


def _personalise(template_str: str, first_name: str, company: str, post_snippet: str) -> str:
    return (
        template_str
        .replace("{{first_name}}", first_name)
        .replace("{{company}}", company)
        .replace("{{post_snippet}}", post_snippet)
    )


def _send_one_sync_with_reply(to_email: str, to_name: str, subject: str, body: str, reply_to: str = "") -> None:
    sender_email, sender_name = _get_sender()
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"name": to_name, "email": to_email}],
        "cc": [{"name": "Deepti", "email": "deepti@decisionpinnacle.com"}],
        "subject": subject,
        "textContent": body,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    resp = requests.post(BREVO_URL, json=payload, headers=_get_headers(), timeout=30)
    _check_resp(resp)


async def run_brevo_sender(
    posts: list[dict],
    master_ws,
    daily_ws,
    emit,
    daily_cap: int | None = None,
    delay_seconds: int = 2,
    dry_run: bool = False,
    excluded_domains: list[str] | None = None,
    reply_to: str = "",
) -> dict:
    effective_cap = daily_cap if daily_cap is not None else DAILY_EMAIL_CAP
    effective_excluded = excluded_domains or []
    dry_label = " [DRY RUN]" if dry_run else ""

    await emit({"event": "stage_start", "stage": 8, "name": "Email Sender",
                "message": f"Sending personalised emails via Brevo{dry_label}..."})

    templates = _load_templates()
    sent_count = 0
    failed_count = 0
    capped = False
    auth_failed = False

    sendable = [p for p in posts if p.get("_final_email") and p.get("_lead_status", "REAL") == "REAL"]

    # For a REAL (non-dry) lead, the Sent Status column must only ever show
    # exactly "SENT" or "NO_EMAIL" — never CAPPED/FAILED/SKIPPED_* internal
    # reasons. Those specific reasons are still tracked (via failed_count/
    # capped, and written into the Error column below) for real reporting —
    # they just don't leak into the simplified Sent Status value itself.
    for post in sendable:
        if auth_failed:
            post["_sent_status"] = "NO_EMAIL"
            post["_error"] = "Not sent — Brevo auth failure earlier in this run"
            continue

        if sent_count >= effective_cap:
            post["_sent_status"] = "NO_EMAIL"
            post["_error"] = "Not sent — daily send cap reached"
            capped = True
            continue

        email = post["_final_email"]
        if not EMAIL_RE.match(email):
            post["_sent_status"] = "NO_EMAIL"
            post["_error"] = f"Invalid email format: {email}"
            log.warning(f"Invalid email format skipped: {email}")
            continue

        domain = email.split("@")[-1].lower()
        if any(domain == excl or domain.endswith("." + excl) for excl in effective_excluded):
            post["_sent_status"] = "NO_EMAIL"
            post["_error"] = f"Excluded domain: {domain}"
            log.info(f"Skipped excluded domain: {domain}")
            continue

        from post_fields import get_content, get_author_name, get_author_headline
        name = get_author_name(post)
        headline = get_author_headline(post)
        first_name = name.split()[0].capitalize() if name.split() else "there"
        company = _extract_company(headline)
        post_snippet = get_content(post)[:100].replace("\n", " ")
        category = post.get("_category", "Generic")

        # Fall back to Generic per-field (not per-category) — a category
        # can exist as a key with blank subject/body (e.g. a newly added
        # category whose template hasn't been written yet), and templates.get(category)
        # returns that truthy-but-empty dict, so `or templates.get("Generic")`
        # never even runs. Checking subject/body individually prevents
        # sending a blank subject to Brevo (which rejects it with a 400).
        tmpl = templates.get(category) or {}
        generic_tmpl = templates.get("Generic") or {}
        subject_raw = tmpl.get("subject") or generic_tmpl.get("subject") or "Introduction — Decision Pinnacle"
        body_raw = tmpl.get("body") or generic_tmpl.get("body") or ""
        subject = _personalise(subject_raw, first_name, company, post_snippet)
        body = _personalise(body_raw, first_name, company, post_snippet)

        if dry_run:
            post["_sent_status"] = "DRY_RUN"
            post["_template_sent"] = category
            post["_sent_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_count += 1
            log.info(f"[DRY RUN] Would send to {email} ({category})")
            await emit({"event": "lead", "name": name, "headline": headline,
                        "category": category, "email": email, "status": "DRY_RUN"})
            await asyncio.sleep(0.1)
            continue

        for attempt in range(2):
            try:
                await asyncio.to_thread(_send_one_sync_with_reply, email, name, subject, body, reply_to)
                post["_sent_status"] = "SENT"
                post["_template_sent"] = category
                post["_sent_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sent_count += 1
                log.info(f"Email sent to {email} ({category})")
                await emit({"event": "lead", "name": name, "headline": headline,
                            "category": category, "email": email, "status": "SENT"})
                break
            except PermissionError as e:
                # IP restriction or bad API key — stop immediately, no point retrying
                err_msg = str(e)
                post["_sent_status"] = "NO_EMAIL"
                post["_error"] = err_msg[:200]
                failed_count += 1
                auth_failed = True
                log.error(f"Brevo auth failed — stopping all sends: {err_msg}")
                await emit({"event": "log", "level": "ERROR", "message": f"❌ Brevo auth error: {err_msg}"})
                break
            except OverflowError:
                post["_sent_status"] = "NO_EMAIL"
                post["_error"] = "Not sent — Brevo daily send limit reached"
                capped = True
                await emit({"event": "progress", "stage": 8, "message": "Brevo daily send limit reached — stopping"})
                log.warning("Brevo daily limit hit")
                break
            except ConnectionError:
                if attempt == 0:
                    await emit({"event": "progress", "stage": 8, "message": "Brevo rate limit — waiting 60s..."})
                    await asyncio.sleep(60)
                else:
                    post["_sent_status"] = "NO_EMAIL"
                    post["_error"] = "Brevo rate limit on retry"
                    failed_count += 1
                    break
            except Exception as e:
                post["_sent_status"] = "NO_EMAIL"
                post["_error"] = str(e)[:200]
                failed_count += 1
                log.error(f"Email send failed for {email}: {e}")
                break

        if capped or auth_failed:
            break

        await asyncio.sleep(max(1, delay_seconds))

    metric = f"{sent_count} sent, {failed_count} failed"
    if auth_failed:
        metric += " (stopped — Brevo auth error)"
    await emit({
        "event": "stage_complete",
        "stage": 8,
        "name": "Email Sender",
        "metric": metric,
        "sent": sent_count,
        "failed": failed_count,
        "capped": capped,
    })
    log.info(f"STAGE 8 | Brevo: {sent_count} sent, {failed_count} failed, capped={capped}, auth_failed={auth_failed}")
    return {"sent": sent_count, "failed": failed_count, "capped": capped, "auth_failed": auth_failed}
