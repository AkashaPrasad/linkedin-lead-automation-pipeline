import asyncio
from logger import get_logger
from post_fields import get_post_url

log = get_logger("dedup")


def _get_seen_post_urls_sync(worksheet) -> set:
    """
    Read all rows from Master and return the set of POST URLs that have
    already been ACTUALLY processed (not dry runs).

    Column B (index 1, 0-based) = Post URL
    Column R (index 17, 0-based) = Sent Status

    This dedupes by the exact post — not by author — so a person who posts
    twice about two different needs (e.g. once about AI video generation,
    once about performance marketing) is never silently dropped as a
    "duplicate" before we even see what the second post is asking for.
    Only a literal re-scrape of a post we've already fully processed is
    skipped here; distinguishing "same author, genuinely new ask" from
    "same author, same ask repeated" happens later, after classification,
    in stages/repeat_lead_filter.py — that's where we actually know what
    each post is asking for.

    We exclude DRY_RUN rows so that dry-run leads can be re-processed on the
    next real run without being blocked by deduplication.
    """
    try:
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return set()
        seen = set()
        for row in all_rows[1:]:  # skip header
            if len(row) < 2:
                continue
            url = row[1].strip()
            sent_status = row[17].strip() if len(row) > 17 else ""
            # Only count as "seen" if it was a real send attempt (not dry run)
            if url and sent_status != "DRY_RUN":
                seen.add(url)
        return seen
    except Exception:
        return set()


async def run_deduplication(posts: list[dict], master_ws, emit) -> list[dict]:
    await emit({"event": "stage_start", "stage": 2, "name": "Deduplication",
                "message": "Checking for exact reposts already processed (ignoring dry-run entries)..."})

    seen_urls = await asyncio.to_thread(_get_seen_post_urls_sync, master_ws)

    if not seen_urls:
        await emit({"event": "progress", "stage": 2,
                    "message": "Master sheet is empty — processing all posts (first run)"})

    new_posts = []
    duplicates = 0
    for post in posts:
        url = get_post_url(post)
        if url and url in seen_urls:
            duplicates += 1
        else:
            new_posts.append(post)

    await emit({
        "event": "stage_complete",
        "stage": 2,
        "name": "Deduplication",
        "metric": f"{len(new_posts)} new posts ({duplicates} exact reposts removed)",
        "duplicates_removed": duplicates,
        "new_leads": len(new_posts),
    })
    log.info(f"STAGE 2 | Dedup: {duplicates} exact reposts removed, {len(new_posts)} new")
    return new_posts
