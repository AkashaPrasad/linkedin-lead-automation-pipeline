import asyncio
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

# Maps our postedLimit values to LinkedIn's own search URL datePosted param
_DATE_POSTED_MAP = {
    "24h": "past-24h",
    "week": "past-week",
    "month": "past-month",
}


def _build_search_url(query: str, posted_limit: str) -> str:
    params = {"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"}
    date_posted = _DATE_POSTED_MAP.get(posted_limit)
    if date_posted:
        params["datePosted"] = date_posted
    return "https://www.linkedin.com/search/results/content/?" + urllib.parse.urlencode(params)


def _build_cookie_run_input(cfg: dict, query: str) -> dict:
    scraping = cfg.get("scraping", {})
    posted_limit = scraping.get("posted_limit", "month")
    cookie_value = get_linkedin_cookie()
    if not cookie_value:
        raise RuntimeError(
            "scraping.use_cookie_actor is enabled but LINKEDIN_COOKIE is not configured"
        )
    return {
        "urls": [_build_search_url(query, posted_limit)],
        "cookie": [{"name": "li_at", "value": cookie_value, "domain": ".linkedin.com", "path": "/"}],
        "userAgent": _COOKIE_ACTOR_USER_AGENT,
        "proxy": {"useApifyProxy": True},
        "limitPerSource": scraping.get("max_posts_per_query", 50),
        "deepScrape": False,
    }


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
