import asyncio
from logger import get_logger
from post_fields import get_author_url

log = get_logger("repeat_lead")


def _get_contacted_categories_sync(worksheet) -> dict:
    """
    Reads Master and returns {author_linkedin_url: {category, ...}} for every
    author who has already been contacted (excluding dry runs) — the set of
    services they've already been reached out about.

    Column D (index 3) = LinkedIn URL (author profile)
    Column O (index 14) = Category
    Column R (index 17) = Sent Status
    """
    try:
        all_rows = worksheet.get_all_values()
        if len(all_rows) <= 1:
            return {}
        contacted: dict[str, set] = {}
        for row in all_rows[1:]:
            if len(row) <= 17:
                continue
            url = row[3].strip()
            category = row[14].strip()
            sent_status = row[17].strip()
            if not url or not category or sent_status == "DRY_RUN":
                continue
            contacted.setdefault(url, set()).add(category)
        return contacted
    except Exception:
        return {}


async def check_repeat_leads(real_posts: list[dict], master_ws, emit) -> tuple[list[dict], list[dict], dict]:
    """
    Runs after AI classification, when we finally know what each post is
    actually asking for. Same author + same category already contacted
    (excluding dry runs) = a true duplicate ask, held back from re-sending.
    Same author + a DIFFERENT category = a genuinely new opportunity (e.g.
    they previously asked about AI video generation, now asking about
    performance marketing) — this is exactly the case that used to be
    silently dropped by the old author-only dedup in Stage 2, so it now
    passes through fully, just flagged as a repeat contact for visibility.

    The contacted-categories map is updated in-memory as we go (not just
    read once from Master) — so if the SAME author shows up twice within
    this single run (e.g. two overlapping search queries both surface
    their posts), the second occurrence is checked against the first,
    not just against previous runs.
    """
    contacted_map = await asyncio.to_thread(_get_contacted_categories_sync, master_ws)

    passed = []
    duplicates = []
    new_author_count = 0
    repeat_new_ask_count = 0
    duplicate_ask_count = 0

    for post in real_posts:
        author_url = get_author_url(post)
        category = (post.get("_category") or "Generic").strip()

        prior_categories = contacted_map.get(author_url) if author_url else None

        if not author_url or not prior_categories:
            post["_repeat_lead"] = "No"
            new_author_count += 1
            passed.append(post)
            if author_url:
                contacted_map.setdefault(author_url, set()).add(category)
            continue

        if category in prior_categories:
            post["_lead_status"] = f"SKIPPED: Duplicate - Already contacted for {category}"
            post["_repeat_lead"] = f"Duplicate (already contacted for {category})"
            duplicate_ask_count += 1
            duplicates.append(post)
        else:
            prior_label = ", ".join(sorted(prior_categories))
            post["_repeat_lead"] = f"Yes — new ask (previously: {prior_label})"
            repeat_new_ask_count += 1
            passed.append(post)
            contacted_map[author_url].add(category)

    stats = {
        "total": len(real_posts),
        "new_authors": new_author_count,
        "repeat_new_ask": repeat_new_ask_count,
        "duplicate_same_ask": duplicate_ask_count,
    }

    if stats["total"]:
        await emit({
            "event": "progress",
            "stage": 4,
            "message": (
                f"Repeat lead check: {stats['total']} checked — {new_author_count} new, "
                f"{repeat_new_ask_count} repeat contacts with a new ask, "
                f"{duplicate_ask_count} duplicate asks held back"
            ),
        })
    log.info(
        f"Repeat lead check: {new_author_count} new authors, "
        f"{repeat_new_ask_count} repeat authors with a new ask (kept), "
        f"{duplicate_ask_count} duplicate same-category asks (held back)"
    )
    return passed, duplicates, stats
