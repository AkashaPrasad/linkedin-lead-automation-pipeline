import asyncio
from datetime import datetime
from logger import get_logger
from config import GOOGLE_SHEET_ID, service_account_path

log = get_logger("sheets")

HEADERS = [
    "Post Content", "Post URL", "Author Name", "LinkedIn URL", "Location (Country)",
    "Author Headline", "Company Name", "Posted Date", "Search Query", "Email From Post",
    "Contact Method", "Apollo Email", "Final Email", "Has Email", "Category",
    "Lead Status", "Template Sent", "Sent Status", "Sent Timestamp", "Error",
    "Repeat Lead",
]

COLUMNS = {
    "post_content": 0, "post_url": 1, "author_name": 2, "linkedin_url": 3,
    "location_country": 4, "author_headline": 5, "company_name": 6, "posted_date": 7,
    "search_query": 8, "email_from_post": 9, "contact_method": 10, "apollo_email": 11,
    "final_email": 12, "has_email": 13, "category": 14, "lead_status": 15,
    "template_sent": 16, "sent_status": 17, "sent_timestamp": 18, "error": 19,
    "repeat_lead": 20,
}


def _open_sheets_sync():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(service_account_path()), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    return sh


def _ensure_worksheet_sync(sh, tab_name: str):
    try:
        ws = sh.worksheet(tab_name)
        return ws
    except Exception:
        ws = sh.add_worksheet(title=tab_name, rows=2000, cols=len(HEADERS))
        return ws


def _ensure_headers_sync(ws) -> int:
    """Ensure header row exists and is up to date. Returns number of existing
    rows (including header). Data rows are always written in HEADERS column
    order regardless of what the sheet's header row says, so if the header
    row is missing a newer column (e.g. a sheet created before "Contact
    Method" or "Repeat Lead" existed), we refresh row 1 in place — this only
    rewrites the label text, never touches any data row.

    Also widens the sheet's column count if it's narrower than HEADERS —
    older sheets were created with a fixed column count, and writing data
    into a column beyond that raises a Sheets API "exceeds grid limits"
    error instead of silently expanding."""
    try:
        if ws.col_count < len(HEADERS):
            ws.resize(cols=len(HEADERS))
    except Exception as e:
        log.warning(f"Could not widen sheet columns: {e}")

    try:
        all_vals = ws.get_all_values()
    except Exception:
        all_vals = []
    first_cell = all_vals[0][0] if (all_vals and all_vals[0]) else ""
    if not first_cell or first_cell != HEADERS[0]:
        # Clear any blank rows first, then insert headers
        try:
            if all_vals:
                ws.clear()
        except Exception:
            pass
        ws.insert_row(HEADERS, 1)
        return 1
    if all_vals[0] != HEADERS:
        ws.update("A1", [HEADERS])
    return len(all_vals)


def _post_to_row(post: dict) -> list:
    from post_fields import get_content, get_post_url, get_author_name, get_author_url, get_author_headline, get_posted_date
    return [
        get_content(post),
        get_post_url(post),
        get_author_name(post),
        get_author_url(post),
        post.get("_location_country") or "",
        get_author_headline(post),
        post.get("_company_name") or "",
        get_posted_date(post),
        post.get("_search_query") or "",
        post.get("_email_in_post") or "",
        post.get("_contact_method") or "",
        "",  # Apollo email — filled later
        "",  # Final email — filled later
        "YES" if post.get("_email_in_post") else "NO",
        post.get("_category") or "Generic",
        post.get("_lead_status") or "REAL",
        "",  # Template sent
        # Sent Status starts blank for EVERY row — a skipped (non-REAL) lead
        # stays blank permanently (send stages never touch it); a REAL lead
        # gets this overwritten at finalize with exactly "SENT" or
        # "NO_EMAIL" once Stages 6-8 resolve it. No "PENDING" placeholder.
        "",
        "",  # Sent timestamp
        "",  # Error
        post.get("_repeat_lead") or "No",
    ]


def _batch_append_sync(ws, rows: list[list]):
    from gspread.utils import InsertDataOption
    for i in range(0, len(rows), 50):
        chunk = rows[i:i + 50]
        # insert_data_option is NOT optional here — the Sheets API's default
        # for values.append is OVERWRITE (it heuristically detects "the
        # table" and overwrites whatever comes after it), not "add new
        # rows". Without INSERT_ROWS explicit, an ambiguous table-boundary
        # detection can silently overwrite an existing row instead of
        # appending after it — this caused real, confirmed data loss in the
        # separate Manual Leads sheet before it was caught and fixed here too.
        ws.append_rows(chunk, value_input_option="RAW", insert_data_option=InsertDataOption.insert_rows)
        if i + 50 < len(rows):
            import time
            time.sleep(1)


def _update_columns_sync(ws, posts: list[dict], start_row: int):
    """Write final email/status columns back to the rows we just appended."""
    try:
        updates = []
        for i, post in enumerate(posts):
            row = start_row + i
            row_vals = [
                post.get("_apollo_email") or "",
                post.get("_final_email") or "",
                post.get("_has_email") or "NO",
                post.get("_category") or "Generic",
                post.get("_lead_status") or "REAL",
                post.get("_template_sent") or "",
                # By finalize time every REAL lead must be resolved to
                # exactly "SENT" or "NO_EMAIL" — if _sent_status is somehow
                # still unset here, "NO_EMAIL" is the correct default (no
                # successful send happened), never "PENDING".
                post.get("_sent_status") or "NO_EMAIL",
                post.get("_sent_timestamp") or "",
                post.get("_error") or "",
            ]
            updates.append({"range": f"L{row}:T{row}", "values": [row_vals]})

        if updates:
            for chunk in [updates[i:i + 50] for i in range(0, len(updates), 50)]:
                ws.batch_update(chunk, value_input_option="RAW")
    except Exception as e:
        log.warning(f"Sheet column update warning: {e}")


async def open_sheets(emit=None):
    sa_path = service_account_path()
    if not sa_path.exists():
        raise RuntimeError("service_account.json not found in backend/ folder")
    try:
        sh = await asyncio.to_thread(_open_sheets_sync)
    except Exception as e:
        raise RuntimeError(f"Google Sheets auth failed — check service_account.json: {e}")
    return sh


async def run_sheets_writer(
    real_posts: list[dict],
    skipped_posts: list[dict],
    sh,
    emit,
    dry_run: bool = False,
) -> tuple[object, object, list[dict], int | None, int]:
    """
    Returns: (master_ws, daily_ws, all_posts, master_start_row, daily_start_row)

    Master is NEVER written here — only truly SENT leads get appended to
    Master, and only after Stage 8 (Brevo) has confirmed the send (see
    append_sent_to_master below). Writing skipped/no-email/pending leads to
    Master would make it look like we'd "contacted" someone we never
    actually emailed, which both pollutes the sheet and causes
    repeat_lead_filter.py to wrongly treat them as already-contacted,
    silently blocking a real future outreach attempt. master_start_row is
    therefore always None — the daily tab still gets every row (real +
    skipped) for full audit visibility.
    daily_start_row is the 1-indexed row where the new real_posts begin in the daily tab.
    """
    today = datetime.now().strftime("%d-%b-%Y")

    daily_tab = f"[DRY] {today}" if dry_run else today
    mode_msg = "[DRY RUN] " if dry_run else ""
    await emit({"event": "stage_start", "stage": 5, "name": "Google Sheets",
                "message": f"{mode_msg}Writing leads to '{daily_tab}'..."})

    daily_ws = await asyncio.to_thread(_ensure_worksheet_sync, sh, daily_tab)
    # Get existing row count BEFORE appending so we know where new rows start
    daily_existing = await asyncio.to_thread(_ensure_headers_sync, daily_ws)

    all_posts = real_posts + skipped_posts
    rows = [_post_to_row(p) for p in all_posts]

    master_ws = await asyncio.to_thread(_ensure_worksheet_sync, sh, "Master")
    await asyncio.to_thread(_ensure_headers_sync, master_ws)

    if rows:
        await asyncio.to_thread(_batch_append_sync, daily_ws, rows)
        # daily_start_row = first row of the REAL posts in the daily tab (1-indexed)
        daily_start_row = daily_existing + 1
    else:
        daily_start_row = daily_existing + 1

    await emit({
        "event": "stage_complete",
        "stage": 5,
        "name": "Google Sheets",
        "metric": f"{mode_msg}{len(rows)} rows → '{daily_tab}'",
        "rows_written": len(rows),
    })
    log.info(f"STAGE 5 | Sheets: {len(rows)} rows → '{daily_tab}' (Master untouched until Stage 8 confirms sends)")
    return master_ws, daily_ws, all_posts, None, daily_start_row


async def finalize_sheet_columns(daily_ws, real_posts: list[dict], daily_start_row: int):
    """Update columns L–T with final Apollo/email/send data for real_posts, in the daily tab."""
    if real_posts:
        await asyncio.to_thread(_update_columns_sync, daily_ws, real_posts, daily_start_row)


def _post_to_master_row(post: dict) -> list:
    """Builds a Master row for a lead that Stage 8 (Brevo) has already
    confirmed was actually SENT — every column is filled with its final
    value in one shot, since Apollo/email-decision/Brevo have all already
    run by the time this is called. Unlike _post_to_row, nothing here is
    a placeholder to be patched in later."""
    from post_fields import get_content, get_post_url, get_author_name, get_author_url, get_author_headline, get_posted_date
    return [
        get_content(post),
        get_post_url(post),
        get_author_name(post),
        get_author_url(post),
        post.get("_location_country") or "",
        get_author_headline(post),
        post.get("_company_name") or "",
        get_posted_date(post),
        post.get("_search_query") or "",
        post.get("_email_in_post") or "",
        post.get("_contact_method") or "",
        post.get("_apollo_email") or "",
        post.get("_final_email") or "",
        post.get("_has_email") or "NO",
        post.get("_category") or "Generic",
        post.get("_lead_status") or "REAL",
        post.get("_template_sent") or "",
        post.get("_sent_status") or "SENT",
        post.get("_sent_timestamp") or "",
        post.get("_error") or "",
        post.get("_repeat_lead") or "No",
    ]


async def append_sent_to_master(master_ws, posts: list[dict]) -> int:
    """Appends ONLY the posts Stage 8 actually sent an email for to Master.
    This is the sole path by which a row ever lands in Master — nothing
    skipped, and nothing real-but-no-email, ever gets written here."""
    sent_posts = [p for p in posts if p.get("_sent_status") == "SENT"]
    if not sent_posts:
        return 0
    rows = [_post_to_master_row(p) for p in sent_posts]
    await asyncio.to_thread(_batch_append_sync, master_ws, rows)
    log.info(f"Master: appended {len(rows)} SENT leads")
    return len(rows)
