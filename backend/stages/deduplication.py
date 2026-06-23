import asyncio
from logger import get_logger
from post_fields import get_author_url

log = get_logger("dedup")


def _get_seen_urls_sync(worksheet) -> set:
    """
    Read all rows from Master and return the set of LinkedIn URLs that have
    already been ACTUALLY processed (not dry runs).

    Column D (index 3, 0-based) = LinkedIn URL
    Column N (index 13, 0-based) = Sent Status

    We exclude DRY_RUN rows so that dry-run leads can be re-processed on the
    next real run without being blocked by deduplication.
    """
    try:
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return set()
        seen = set()
        for row in all_rows[1:]:  # skip header
            if len(row) < 4:
                continue
            url = row[3].strip()
            sent_status = row[13].strip() if len(row) > 13 else ""
            # Only count as "seen" if it was a real send attempt (not dry run)
            if url and sent_status != "DRY_RUN":
                seen.add(url)
        return seen
    except Exception:
        return set()


async def run_deduplication(posts: list[dict], master_ws, emit) -> list[dict]:
    await emit({"event": "stage_start", "stage": 2, "name": "Deduplication",
                "message": "Checking for duplicate LinkedIn profiles (ignoring dry-run entries)..."})

    seen_urls = await asyncio.to_thread(_get_seen_urls_sync, master_ws)

    if not seen_urls:
        await emit({"event": "progress", "stage": 2,
                    "message": "Master sheet is empty — processing all posts (first run)"})

    new_posts = []
    duplicates = 0
    for post in posts:
        url = get_author_url(post)
        if url and url in seen_urls:
            duplicates += 1
        else:
            new_posts.append(post)

    await emit({
        "event": "stage_complete",
        "stage": 2,
        "name": "Deduplication",
        "metric": f"{len(new_posts)} new leads ({duplicates} duplicates removed)",
        "duplicates_removed": duplicates,
        "new_leads": len(new_posts),
    })
    log.info(f"STAGE 2 | Dedup: {duplicates} removed, {len(new_posts)} new")
    return new_posts
