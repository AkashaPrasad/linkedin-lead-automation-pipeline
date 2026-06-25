"""
Promote a dry-run tab to a real send.

Reads rows directly out of an existing "[DRY] <date>" tab, reconstructs
minimal post objects from them, and runs them through the SAME Stage 6→9
functions (Apollo enrichment → email decision → Brevo send → finalize) that
a normal real run uses — with dry_run=False. This processes exactly the
leads already sitting in that tab; it never re-scrapes Apify.

Apollo enrichment is forced ON for this action regardless of the saved
admin toggle, since promoting a dry run always means "fill missing emails,
then send."
"""
import asyncio
import time
from logger import get_logger
from stages.sheets_writer import open_sheets, run_sheets_writer, HEADERS, COLUMNS
from pipeline import _run_stages_6_to_9
from stages.alerts import send_alert

log = get_logger("promote")


def _row_to_post(row: list[str], row_index: int) -> dict:
    def col(name: str) -> str:
        idx = COLUMNS[name]
        return row[idx].strip() if idx < len(row) else ""

    return {
        "content": col("post_content"),
        "url": col("post_url"),
        "authorFullName": col("author_name"),
        "authorProfileUrl": col("linkedin_url"),
        "authorHeadline": col("author_headline"),
        "_location_country": col("location_country") or None,
        "_company_name": col("company_name") or None,
        "postedAt": col("posted_date"),
        "_search_query": col("search_query"),
        "_email_in_post": col("email_from_post") or None,
        "_contact_method": col("contact_method"),
        "_apollo_email": col("apollo_email") or None,
        "_category": col("category") or "Generic",
        "_lead_status": "REAL",
        "_dry_row_index": row_index,
    }


def _read_promotable_posts_sync(ws) -> list[dict]:
    """Every row marked REAL during the dry run is promotable, regardless of
    its Sent Status — that includes DRY_RUN (already had an email) AND
    NO_EMAIL (never got an email because Apollo enrichment was off; this is
    exactly the case that needs Apollo now). Rows the AI/location filter
    already skipped (Lead Status starts with "SKIPPED:") are left alone,
    and anything already SENT or PROMOTED is never re-promoted."""
    all_vals = ws.get_all_values()
    if len(all_vals) <= 1:
        return []
    posts = []
    for i, row in enumerate(all_vals[1:], start=2):  # 1-indexed; row 1 is header
        if len(row) <= COLUMNS["sent_status"]:
            continue
        sent_status = row[COLUMNS["sent_status"]].strip()
        lead_status = row[COLUMNS["lead_status"]].strip() if len(row) > COLUMNS["lead_status"] else ""
        if lead_status != "REAL" or sent_status in ("SENT", "PROMOTED"):
            continue
        posts.append(_row_to_post(row, i))
    return posts


def count_promotable_sync(tab_name: str) -> dict:
    """Read-only check — counts how many rows qualify and how many already
    have an email, without writing or sending anything."""
    import gspread
    from google.oauth2.service_account import Credentials
    from config import GOOGLE_SHEET_ID, service_account_path
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(service_account_path()), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = sh.worksheet(tab_name)
    posts = _read_promotable_posts_sync(ws)
    with_email = sum(1 for p in posts if p.get("_email_in_post") or p.get("_apollo_email"))
    return {
        "tab_name": tab_name,
        "promotable": len(posts),
        "already_have_email": with_email,
        "need_apollo": len(posts) - with_email,
    }


def _mark_promoted_sync(ws, row_indices: list[int]):
    """Marks the source dry-run rows as PROMOTED so this tab is never
    accidentally promoted twice. Only touches the Sent Status column."""
    col_letter = chr(ord("A") + COLUMNS["sent_status"])
    updates = [{"range": f"{col_letter}{i}", "values": [["PROMOTED"]]} for i in row_indices]
    if updates:
        for chunk in [updates[i:i + 50] for i in range(0, len(updates), 50)]:
            ws.batch_update(chunk, value_input_option="RAW")


async def promote_dry_run_async(emit, tab_name: str) -> None:
    from admin_config import load as load_cfg
    cfg = load_cfg()
    # Force Apollo enrichment on for this action regardless of the saved
    # toggle — the whole point of promoting is filling missing emails first.
    cfg = {**cfg, "enrichment": {**cfg.get("enrichment", {}), "apollo_enabled": True}}

    pipeline_start = time.time()
    await send_alert(f"🚀 Promoting dry-run tab '{tab_name}' to a real send")
    log.info(f"Promoting dry-run tab '{tab_name}'")

    sh = await open_sheets(emit)
    try:
        dry_ws = await asyncio.to_thread(sh.worksheet, tab_name)
    except Exception:
        raise RuntimeError(f"Tab '{tab_name}' not found in the sheet")

    real_posts = await asyncio.to_thread(_read_promotable_posts_sync, dry_ws)

    if not real_posts:
        await emit({"event": "complete", "scraped": 0, "real": 0, "with_email": 0,
                    "sent": 0, "failed": 0, "no_email": 0, "duration_min": 0})
        await send_alert(f"✅ Promote complete — no eligible DRY_RUN/REAL rows found in '{tab_name}'")
        return

    stats = {"scraped": len(real_posts), "real": len(real_posts), "enriched": 0, "sent": 0}
    await emit({"event": "stats", **stats})
    await send_alert(f"✅ Found {len(real_posts)} leads to promote from '{tab_name}'")

    # Write fresh rows into Master + today's real daily tab — mirrors what a
    # normal Stage 5 write would have done for a real (non-dry) run.
    master_ws, daily_ws, all_posts, master_start_row, daily_start_row = await run_sheets_writer(
        real_posts, [], sh, emit, dry_run=False
    )

    await _run_stages_6_to_9(
        emit, all_posts, master_ws, daily_ws,
        master_start_row, daily_start_row,
        cfg, False, stats, pipeline_start,
    )

    row_indices = [p["_dry_row_index"] for p in real_posts]
    await asyncio.to_thread(_mark_promoted_sync, dry_ws, row_indices)
    log.info(f"Marked {len(row_indices)} rows as PROMOTED in '{tab_name}'")
