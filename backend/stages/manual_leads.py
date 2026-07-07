"""
Manual Leads sheet — real leads that ended up with NO_EMAIL (Apollo found
nothing and the post itself had no email) still deserve outreach, just via a
manual LinkedIn DM instead of an automated email. Those leads get written to
a SEPARATE spreadsheet (MANUAL_LEADS_SHEET_ID) with a colored Status dropdown
("Not sent" red / "Sent" green / "Skipped" gray) so a human can work through
them, mark each one once DM'd, or mark it "Skipped" if it turns out not to be
a real lead after all. Before every real pipeline run, we read that sheet and
transfer any row marked "Sent" (and not yet transferred) into the Master
sheet — Master's sent-only contract (see sheets_writer.append_sent_to_master)
treats a manual DM exactly like an email send: it's a real, successful
contact. "Skipped" rows are never written to Master — the sync only ever
looks for STATUS_SENT (see _sync_sent_to_master_sync), so anything else,
"Not sent" or "Skipped" alike, is simply left alone.
"""
import asyncio
from logger import get_logger
from config import GOOGLE_SHEET_ID, MANUAL_LEADS_SHEET_ID, service_account_path, now_ist
from stages.sheets_writer import HEADERS as MASTER_HEADERS

log = get_logger("manual_leads")

HEADERS = [
    "Post Content", "Post URL", "Author Name", "LinkedIn URL", "Author Headline",
    "Company Name", "Posted Date", "Search Query", "Category", "Status",
    "Sent Timestamp", "Master Synced",
]
COLUMNS = {
    "post_content": 0, "post_url": 1, "author_name": 2, "linkedin_url": 3,
    "author_headline": 4, "company_name": 5, "posted_date": 6, "search_query": 7,
    "category": 8, "status": 9, "sent_timestamp": 10, "master_synced": 11,
}

STATUS_NOT_SENT = "Not sent"
STATUS_SENT = "Sent"
# For a post that turns out NOT to be a real lead once a human looks at it —
# never synced to Master (see _sync_sent_to_master_sync, which only ever
# looks for STATUS_SENT rows; anything else, including this one, is ignored).
STATUS_SKIPPED = "Skipped"

_RED_BG = {"red": 0.96, "green": 0.80, "blue": 0.80}
_RED_TEXT = {"red": 0.60, "green": 0.0, "blue": 0.0}
_GREEN_BG = {"red": 0.80, "green": 0.94, "blue": 0.80}
_GREEN_TEXT = {"red": 0.0, "green": 0.45, "blue": 0.0}
_GRAY_BG = {"red": 0.88, "green": 0.88, "blue": 0.88}
_GRAY_TEXT = {"red": 0.40, "green": 0.40, "blue": 0.40}


def is_configured() -> bool:
    return bool(MANUAL_LEADS_SHEET_ID)


def _open_sync():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(service_account_path()), scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MANUAL_LEADS_SHEET_ID)
    return sh.get_worksheet(0)


def _setup_sheet_sync(ws) -> None:
    """Ensures the header row is correct and — ONLY the very first time —
    sets up the Status column's dropdown and red/green conditional
    formatting. NEVER clears the sheet: a fragile "does row 1 exactly match"
    comparison used to gate a destructive ws.clear() call here, which wiped
    every data row (not just the header) on any mismatch — including a
    false mismatch caused by nothing more than a transient/stale read. This
    was a real incident (all backfilled leads were lost). Fixed by (a) never
    calling clear(), only ever overwriting row 1 in place, and (b) detecting
    "first-time setup" via whether conditional format rules already exist on
    this sheet — a durable signal — instead of exact-matching the header row."""
    if first_row := ws.row_values(1):
        if first_row != HEADERS:
            ws.update([HEADERS], "A1")  # fix header in place, never touch other rows
    else:
        ws.update([HEADERS], "A1")

    try:
        meta = ws.spreadsheet.fetch_sheet_metadata()
        sheet_meta = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == ws.id)
        if sheet_meta.get("conditionalFormats"):
            return  # dropdown + colors already set up — never re-apply
    except Exception as e:
        log.warning(f"Manual Leads: could not check existing conditional formats, skipping setup to be safe: {e}")
        return

    sheet_id = ws.id
    status_col = COLUMNS["status"]
    full_range = {
        "sheetId": sheet_id,
        "startRowIndex": 1,
        "startColumnIndex": status_col,
        "endColumnIndex": status_col + 1,
    }

    requests = [
        {
            "setDataValidation": {
                "range": full_range,
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": STATUS_NOT_SENT},
                            {"userEnteredValue": STATUS_SENT},
                            {"userEnteredValue": STATUS_SKIPPED},
                        ],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [full_range],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": STATUS_NOT_SENT}]},
                        "format": {"backgroundColor": _RED_BG, "textFormat": {"foregroundColor": _RED_TEXT, "bold": True}},
                    },
                },
                "index": 0,
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [full_range],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": STATUS_SENT}]},
                        "format": {"backgroundColor": _GREEN_BG, "textFormat": {"foregroundColor": _GREEN_TEXT, "bold": True}},
                    },
                },
                "index": 1,
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [full_range],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": STATUS_SKIPPED}]},
                        "format": {"backgroundColor": _GRAY_BG, "textFormat": {"foregroundColor": _GRAY_TEXT, "bold": True}},
                    },
                },
                "index": 2,
            }
        },
    ]
    ws.spreadsheet.batch_update({"requests": requests})
    log.info("Manual Leads sheet: headers + Status dropdown/colors set up (first run)")


def _get_existing_post_urls_sync(ws) -> set:
    """Post URLs already sitting in the Manual Leads sheet — regardless of
    Status — so a lead that's still "Not sent" (or already "Sent" but not
    yet synced) is never appended a second time on a later run. Master no
    longer contains NO_EMAIL rows (sent-only design), so Stage 2 dedup alone
    can't prevent this; this is a second, independent dedup check specific
    to this sheet."""
    try:
        all_rows = ws.get_all_values()
        if len(all_rows) <= 1:
            return set()
        return {row[1].strip() for row in all_rows[1:] if len(row) > 1 and row[1].strip()}
    except Exception:
        return set()


def _post_to_manual_row(post: dict) -> list:
    from post_fields import get_content, get_post_url, get_author_name, get_author_url, get_author_headline, get_posted_date
    return [
        get_content(post),
        get_post_url(post),
        get_author_name(post),
        get_author_url(post),
        get_author_headline(post),
        post.get("_company_name") or "",
        get_posted_date(post),
        post.get("_search_query") or "",
        post.get("_category") or "Generic",
        STATUS_NOT_SENT,
        "",
        "No",
    ]


async def append_manual_leads(posts: list[dict], emit=None) -> int:
    """Appends real leads that ended up NO_EMAIL to the Manual Leads sheet,
    skipping any post URL already present there from a previous run."""
    if not is_configured():
        return 0
    candidates = [
        p for p in posts
        if p.get("_lead_status") == "REAL" and p.get("_sent_status") == "NO_EMAIL"
    ]
    if not candidates:
        return 0

    try:
        ws = await asyncio.to_thread(_open_sync)
        await asyncio.to_thread(_setup_sheet_sync, ws)
        existing = await asyncio.to_thread(_get_existing_post_urls_sync, ws)

        from post_fields import get_post_url
        new_posts = [p for p in candidates if get_post_url(p) not in existing]
        if not new_posts:
            return 0

        rows = [_post_to_manual_row(p) for p in new_posts]
        # insert_data_option=INSERT_ROWS is required — the Sheets API default
        # (OVERWRITE) can silently clobber an existing row if its table-
        # boundary heuristic is ever ambiguous. This exact gap caused a
        # confirmed real row loss earlier; do not remove this parameter.
        from gspread.utils import InsertDataOption
        await asyncio.to_thread(
            lambda: ws.append_rows(rows, value_input_option="RAW", insert_data_option=InsertDataOption.insert_rows)
        )
        log.info(f"Manual Leads: appended {len(rows)} NO_EMAIL leads for manual LinkedIn DM")
        if emit:
            await emit({"event": "progress", "stage": 9,
                        "message": f"{len(rows)} NO_EMAIL leads written to Manual Leads sheet for LinkedIn DM"})
        return len(rows)
    except Exception as e:
        log.warning(f"Manual Leads: could not append leads: {e}")
        return 0


def _sync_sent_to_master_sync(manual_ws, master_ws) -> int:
    all_rows = manual_ws.get_all_values()
    if len(all_rows) <= 1:
        return 0

    now = now_ist().strftime("%Y-%m-%d %H:%M:%S")
    master_rows = []
    sheet_updates = []

    for i, row in enumerate(all_rows[1:], start=2):  # 1-indexed; row 1 is header
        def col(name):
            idx = COLUMNS[name]
            return row[idx].strip() if idx < len(row) else ""

        status = col("status")
        synced = col("master_synced")
        if status != STATUS_SENT or synced.lower() == "yes":
            continue

        sent_ts = col("sent_timestamp") or now
        master_rows.append([
            col("post_content"),
            col("post_url"),
            col("author_name"),
            col("linkedin_url"),
            "",                              # Location (Country) — unknown for manual leads
            col("author_headline"),
            col("company_name"),
            col("posted_date"),
            col("search_query"),
            "",                              # Email From Post
            "Phone/LinkedIn/Not Specified",  # Contact Method
            "",                              # Apollo Email
            "",                              # Final Email
            "NO",                            # Has Email
            col("category") or "Generic",
            "REAL",                          # Lead Status
            "Manual DM",                     # Template Sent
            "SENT",                          # Sent Status — a manual DM is a real, successful contact
            sent_ts,
            "",                              # Error
            "No",                            # Repeat Lead
        ])
        sheet_updates.append({"row": i, "sent_ts": sent_ts})

    if not master_rows:
        return 0

    assert len(master_rows[0]) == len(MASTER_HEADERS), "Manual-to-Master row width drifted from Master schema"
    from gspread.utils import InsertDataOption
    master_ws.append_rows(master_rows, value_input_option="RAW", insert_data_option=InsertDataOption.insert_rows)

    # Mark each transferred row as synced (and backfill Sent Timestamp if the
    # user left it blank) so it's never transferred twice.
    batch = []
    status_col_letter = chr(ord("A") + COLUMNS["sent_timestamp"])
    synced_col_letter = chr(ord("A") + COLUMNS["master_synced"])
    for u in sheet_updates:
        batch.append({"range": f"{status_col_letter}{u['row']}", "values": [[u["sent_ts"]]]})
        batch.append({"range": f"{synced_col_letter}{u['row']}", "values": [["Yes"]]})
    manual_ws.batch_update(batch, value_input_option="RAW")

    return len(master_rows)


async def sync_sent_to_master(master_ws, emit=None) -> int:
    """Runs before every real pipeline run: any row in the Manual Leads sheet
    marked "Sent" that hasn't already been transferred gets appended to
    Master now, exactly like a successful email send. Safe to call every
    run — already-synced rows are skipped via the Master Synced column."""
    if not is_configured():
        return 0
    try:
        manual_ws = await asyncio.to_thread(_open_sync)
        await asyncio.to_thread(_setup_sheet_sync, manual_ws)
        count = await asyncio.to_thread(_sync_sent_to_master_sync, manual_ws, master_ws)
        if count:
            log.info(f"Manual Leads: synced {count} manually-sent DM leads to Master")
            if emit:
                await emit({"event": "progress", "stage": 0,
                            "message": f"Synced {count} manually-sent LinkedIn DM leads to Master"})
        return count
    except Exception as e:
        log.warning(f"Manual Leads: could not sync sent leads to Master: {e}")
        return 0
