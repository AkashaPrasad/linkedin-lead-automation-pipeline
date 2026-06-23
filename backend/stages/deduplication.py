import asyncio
from logger import get_logger
from post_fields import get_author_url, get_author_headline, get_content

log = get_logger("dedup")

# India location signals — checked against author headline AND post content
# (case-insensitive). The harvestapi/linkedin-post-search actor has no native
# location filter for post search, so this is a post-hoc text-based filter to
# cut out non-Indian posts before they hit the expensive AI filter stage.
INDIA_SIGNALS = [
    "india", "indian", "mumbai", "delhi", "bangalore", "bengaluru",
    "hyderabad", "chennai", "pune", "noida", "gurgaon", "gurugram",
    "kolkata", "ahmedabad", "surat", "jaipur", "lucknow", "chandigarh",
    "india-based", "₹", "inr", "crore", "lakh", "lakhs",
    "d2c india", "dtc india", "ecommerce india", "fmcg india",
]

# Author headline signals that identify the POSTER as an agency/recruiter
# person — only applied to author.info, never to post content (a brand
# founder mentioning "marketing agency" in their post text is a real lead).
AGENCY_AUTHOR_SIGNALS = [
    "founder at", "co-founder at", "director at", "head of",
    "we are a", "our agency", "digital marketing agency",
    "performance marketing agency", "social media agency",
    "branding agency", "creative agency", "marketing agency",
    "agency owner", "agency founder", "managing director at",
    "i help brands", "i help businesses", "helping brands",
    "helping businesses", "growth hacker", "recruiter", "talent acquisition",
    "hr manager", "human resources",
]


def _india_filter_one(post: dict) -> tuple[bool, str]:
    """Returns (passed, reason) for a single post."""
    headline = get_author_headline(post).lower()
    content = get_content(post).lower()

    india_in_headline = any(sig in headline for sig in INDIA_SIGNALS)
    india_in_content = any(sig in content for sig in INDIA_SIGNALS)

    if not india_in_headline and not india_in_content:
        return False, "no India signal"

    agency_author = any(sig in headline for sig in AGENCY_AUTHOR_SIGNALS)
    if agency_author and not india_in_content:
        # Headline screams agency/recruiter and content didn't independently
        # confirm India — reject. If content DID confirm India, post content
        # is ground truth and overrides an ambiguous headline.
        return False, "agency author"

    return True, "passed"


_REASON_LABELS = {
    "no India signal": "No India Signal",
    "agency author": "Agency Author",
}


def _apply_india_filter(posts: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Returns (passed, rejected, stats). Rejected posts are NOT dropped — they're
    tagged with _lead_status so they still show up in the sheet as skipped,
    instead of disappearing before anyone can see why."""
    passed = []
    rejected = []
    reasons = {"no India signal": 0, "agency author": 0}
    for post in posts:
        ok, reason = _india_filter_one(post)
        if ok:
            passed.append(post)
        else:
            reasons[reason] += 1
            post["_lead_status"] = f"SKIPPED: India Filter - {_REASON_LABELS[reason]}"
            post["_filter_reason"] = reason
            rejected.append(post)
    stats = {
        "total": len(posts),
        "passed": len(passed),
        "rejected_no_india": reasons["no India signal"],
        "rejected_agency": reasons["agency author"],
    }
    return passed, rejected, stats


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


async def run_deduplication(posts: list[dict], master_ws, emit) -> tuple[list[dict], list[dict], dict]:
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

    await emit({"event": "progress", "stage": 2,
                "message": f"Applying India location filter to {len(new_posts)} deduplicated posts..."})

    india_passed, india_rejected, india_stats = _apply_india_filter(new_posts)
    pass_rate = round(100 * india_stats["passed"] / india_stats["total"], 1) if india_stats["total"] else 0.0

    await emit({
        "event": "stage_complete",
        "stage": 2,
        "name": "Deduplication",
        "metric": (
            f"{len(new_posts)} new leads ({duplicates} duplicates removed) — "
            f"India filter: {india_stats['passed']} passed, "
            f"{india_stats['rejected_no_india'] + india_stats['rejected_agency']} logged as skipped "
            f"({pass_rate}% pass rate)"
        ),
        "duplicates_removed": duplicates,
        "new_leads": len(new_posts),
        "india_filter": india_stats,
    })
    log.info(
        f"STAGE 2 | Dedup: {duplicates} removed, {len(new_posts)} new | "
        f"India filter: {india_stats['passed']}/{india_stats['total']} passed, rest logged as skipped "
        f"({india_stats['rejected_no_india']} no India signal, "
        f"{india_stats['rejected_agency']} agency author)"
    )
    return india_passed, india_rejected, india_stats
