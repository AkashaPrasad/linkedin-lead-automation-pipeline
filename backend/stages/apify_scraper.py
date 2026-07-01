import asyncio
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from logger import get_logger
from config import APIFY_API_TOKEN, APIFY_ACTOR_ID, APIFY_COOKIE_ACTOR_ID, get_linkedin_cookie

log = get_logger("apify")


# "48h" is not a native Apify postedLimit value — we emulate it below via postedLimitDate.
_VALID_POSTED_LIMITS = {"any", "1h", "24h", "48h", "week", "month", "3months", "6months", "year"}

# curious_coder/linkedin-post-search-scraper requires a userAgent — there's no
# documented default, so we send a standard desktop Chrome string.
_COOKIE_ACTOR_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Maps our postedLimit values to LinkedIn's own search URL datePosted param.
# LinkedIn's search UI has no native "past 48 hours" bucket — "48h" maps to
# the closest broader bucket ("past-week") as a first-pass server-side
# filter. This is NOT the final word on what gets through: _filter_by_actual_date()
# below independently re-checks every post's real timestamp afterward, so a
# too-broad first pass here only means slightly more posts to filter, never
# a stale post slipping past the real cutoff.
_DATE_POSTED_MAP = {
    "1h": "past-24h",
    "24h": "past-24h",
    "48h": "past-week",
    "week": "past-week",
    "month": "past-month",
}

# Hours corresponding to each postedLimit value, used to independently verify
# every scraped post's ACTUAL posted timestamp — never just trust that the
# actor honored the date filter it was given. This is what actually prevents
# stale posts (e.g. an 11-month-old post surfacing despite a 48h filter) from
# reaching the pipeline, regardless of which actor scraped it or whether that
# actor's own date filtering has any gaps.
_POSTED_LIMIT_HOURS = {
    "1h": 1, "24h": 24, "48h": 48, "week": 24 * 7, "month": 24 * 30,
    "3months": 24 * 90, "6months": 24 * 180, "year": 24 * 365,
}


def _compute_scrape_until_date(posted_limit: str) -> str | None:
    """Day-granularity cutoff (YYYY-MM-DD) for the actor's scrapeUntilDate
    input — this makes the actor STOP SCRAPING once it reaches posts older
    than this date, so old posts are never even extracted, instead of being
    pulled and discarded afterward. Coarser than the hour-precise
    _filter_by_actual_date() safety net that still runs afterward, but this
    is what actually saves scrape time/compute by cutting extraction short."""
    import math
    hours = _POSTED_LIMIT_HOURS.get(posted_limit)
    if hours is None:
        return None
    days = max(1, math.ceil(hours / 24))
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    return cutoff_date.strftime("%Y-%m-%d")


def _build_search_url(query: str, posted_limit: str) -> str:
    params = {"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"}
    date_posted = _DATE_POSTED_MAP.get(posted_limit)
    if date_posted:
        params["datePosted"] = date_posted
    # Sort by newest-first — required by the actor for scrapeUntilDate to
    # work at all, and independently important on its own: without an
    # explicit sort, LinkedIn defaults to relevance ranking, which can
    # surface an old-but-highly-relevant post ahead of fresher ones even
    # within a date-restricted bucket. This was very likely a contributing
    # cause of a stale post reaching the pipeline despite a tight window.
    if posted_limit != "any":
        params["sortBy"] = '"date_posted"'
    return "https://www.linkedin.com/search/results/content/?" + urllib.parse.urlencode(params)


def _parse_cookie_export(raw: str) -> list:
    """The actor's own input schema requires the FULL Cookie-Editor export
    (a JSON array of LinkedIn's session cookies — li_at, JSESSIONID, etc.),
    not a single li_at value. A lone li_at is rejected by the actor as
    "invalid cookies" because LinkedIn needs the whole session, not one cookie."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(
            "LINKEDIN_COOKIE is not a valid cookie export. Install the Cookie-Editor "
            "browser extension, log into LinkedIn, click the extension, export the "
            "cookies, and paste the FULL JSON array (not just li_at) into the admin panel."
        )
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError(
            "LINKEDIN_COOKIE must be the full JSON array exported by Cookie-Editor, "
            "not a single cookie value."
        )
    return parsed


def _build_cookie_run_input(cfg: dict, query: str) -> dict:
    scraping = cfg.get("scraping", {})
    posted_limit = scraping.get("posted_limit", "month")
    cookie_raw = get_linkedin_cookie()
    if not cookie_raw:
        raise RuntimeError(
            "scraping.use_cookie_actor is enabled but LINKEDIN_COOKIE is not configured"
        )
    cookie_array = _parse_cookie_export(cookie_raw)
    run_input = {
        "urls": [_build_search_url(query, posted_limit)],
        "cookie": cookie_array,
        "userAgent": _COOKIE_ACTOR_USER_AGENT,
        "proxy": {"useApifyProxy": True},
        "limitPerSource": scraping.get("max_posts_per_query", 50),
        "deepScrape": False,
    }
    scrape_until = _compute_scrape_until_date(posted_limit)
    if scrape_until:
        run_input["scrapeUntilDate"] = scrape_until
    return run_input


def _build_run_input(cfg: dict, query: str) -> dict:
    scraping = cfg.get("scraping", {})
    posted_limit = scraping.get("posted_limit", "month")
    if posted_limit not in _VALID_POSTED_LIMITS:
        log.warning(f"Invalid postedLimit '{posted_limit}', falling back to 'month'")
        posted_limit = "month"
    run_input = {
        "searchQueries": [query],
        "maxPostsPerQuery": scraping.get("max_posts_per_query", 50),
        "sortBy": scraping.get("sort_by", "date"),
    }
    if posted_limit == "48h":
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        run_input["postedLimitDate"] = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        run_input["postedLimit"] = posted_limit
    if scraping.get("author_industry_ids"):
        run_input["authorIndustryIds"] = [str(i) for i in scraping["author_industry_ids"]]
    if scraping.get("author_geo_ids"):
        run_input["authorGeoIds"] = [str(i) for i in scraping["author_geo_ids"]]
    return run_input


def _filter_by_actual_date(posts: list[dict], posted_limit: str) -> tuple[list[dict], int, int]:
    """Independently verifies each post's ACTUAL posted timestamp against
    the configured window — this is the authoritative check, not the actor
    input parameters (which one actor mode was silently not even sending
    for "48h", and neither actor's own date filtering should be trusted
    blindly regardless). Returns (kept, dropped_stale_count, unparseable_count).

    Posts with no parseable date are kept (not dropped) — an actor
    occasionally omitting the date field is a data-quality gap, not
    evidence the post is stale, and dropping them risks losing real leads.
    """
    hours = _POSTED_LIMIT_HOURS.get(posted_limit)
    if hours is None:
        return posts, 0, 0

    from post_fields import get_posted_date
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    kept = []
    dropped_stale = 0
    unparseable = 0
    for p in posts:
        raw = get_posted_date(p)
        if not raw:
            unparseable += 1
            kept.append(p)
            continue
        try:
            normalized = raw.replace("Z", "+00:00")
            posted_at = datetime.fromisoformat(normalized)
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            unparseable += 1
            kept.append(p)
            continue

        if posted_at < cutoff:
            dropped_stale += 1
        else:
            kept.append(p)

    return kept, dropped_stale, unparseable


def _run_apify_sync(run_input: dict, actor_id: str) -> list[dict]:
    from apify_client import ApifyClient
    client = ApifyClient(APIFY_API_TOKEN)
    actor_client = client.actor(actor_id)
    run = actor_client.call(run_input=run_input, timeout_secs=600)
    dataset_client = client.dataset(run["defaultDatasetId"])
    return dataset_client.list_items().items


def _run_apify_for_query_sync(cfg: dict, query: str) -> list[dict]:
    """Runs the actor for a single search query and tags each result with the query
    that produced it, so the sheet can show which keywords are converting best."""
    use_cookies = cfg.get("scraping", {}).get("use_cookie_actor", False)
    if use_cookies:
        run_input = _build_cookie_run_input(cfg, query)
        posts = _run_apify_sync(run_input, APIFY_COOKIE_ACTOR_ID)
    else:
        run_input = _build_run_input(cfg, query)
        posts = _run_apify_sync(run_input, APIFY_ACTOR_ID)
    for p in posts:
        p["_search_query"] = query
    return posts


async def run_apify(emit, cfg: dict | None = None) -> list[dict]:
    if cfg is None:
        from admin_config import load
        cfg = load()

    scraping = cfg.get("scraping", {})
    queries = scraping.get("search_queries") or ["marketing agency"]
    total_cap = scraping.get("total_post_cap", 500)
    min_len = cfg.get("filtering", {}).get("min_post_length", 50)
    use_cookies = scraping.get("use_cookie_actor", False)

    if use_cookies and not get_linkedin_cookie():
        raise RuntimeError(
            "scraping.use_cookie_actor is enabled but no LinkedIn cookie is configured — "
            "set it in the admin panel first"
        )

    mode = "cookie-authenticated" if use_cookies else "no-cookie"
    await emit({"event": "stage_start", "stage": 1, "name": "Apify Scraper",
                "message": f"Scraping LinkedIn with {len(queries)} keywords ({mode} mode)..."})
    await emit({"event": "progress", "stage": 1, "message": "Apify runs started, waiting for completion..."})
    log.info(f"STAGE 1 | Scraping mode: {mode}")

    # Run one Apify call per query (sequentially, on worker threads) so we can tag
    # each post with the exact search query that found it — needed to see which
    # keywords are converting best.
    posts: list[dict] = []
    errors: list[str] = []
    for query in queries:
        try:
            query_posts = await asyncio.to_thread(_run_apify_for_query_sync, cfg, query)
            posts.extend(query_posts)
            await emit({"event": "progress", "stage": 1,
                        "message": f"'{query}' → {len(query_posts)} posts"})
        except Exception as e:
            err = str(e)
            if "actor" in err.lower() and "not found" in err.lower():
                raise RuntimeError("Invalid Apify actor ID in .env")
            errors.append(f"{query}: {err}")
            log.warning(f"Apify query '{query}' failed: {err}")

    if not posts:
        detail = f" ({'; '.join(errors)})" if errors else ""
        raise RuntimeError(f"Apify returned 0 results — no posts found for given search queries{detail}")

    # Deduplicate posts matched by multiple queries, keeping the first query tag
    from post_fields import get_post_url, get_content
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for p in posts:
        url = get_post_url(p)
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(p)
    posts = deduped

    # Filter empty content (HarvestAPI uses 'content' field, not 'text')
    posts = [p for p in posts if get_content(p)]

    # Filter by minimum post length
    if min_len > 0:
        before = len(posts)
        posts = [p for p in posts if len(get_content(p)) >= min_len]
        if before != len(posts):
            await emit({"event": "progress", "stage": 1,
                        "message": f"Filtered {before - len(posts)} posts shorter than {min_len} chars"})

    # Authoritative date check — verifies each post's ACTUAL posted
    # timestamp against the configured window, independent of whether the
    # actor's own date-filter input was honored correctly. This is what
    # prevents a stale post (e.g. months old) from slipping through despite
    # a tight window like "past 48 hours" being selected.
    posted_limit = scraping.get("posted_limit", "month")
    posts, dropped_stale, unparseable = _filter_by_actual_date(posts, posted_limit)
    if dropped_stale:
        await emit({"event": "progress", "stage": 1,
                    "message": f"Filtered {dropped_stale} posts older than the configured '{posted_limit}' window"})
        log.info(f"STAGE 1 | Date check: dropped {dropped_stale} stale posts (window={posted_limit})")
    if unparseable:
        log.warning(f"STAGE 1 | Date check: {unparseable} posts had no parseable posted date — kept, not verified")

    # Apply total cap
    if len(posts) > total_cap:
        posts = posts[:total_cap]
        await emit({"event": "progress", "stage": 1,
                    "message": f"Capped to {total_cap} posts per admin config"})

    await emit({"event": "progress", "stage": 1, "message": f"Retrieved {len(posts)} posts from Apify dataset"})
    await emit({"event": "stage_complete", "stage": 1, "name": "Apify Scraper",
                "metric": f"{len(posts)} posts scraped"})
    log.info(f"STAGE 1 | Apify scraped {len(posts)} posts")
    return posts
