import asyncio
from logger import get_logger
from config import APIFY_API_TOKEN, APIFY_ACTOR_ID

log = get_logger("apify")


_VALID_POSTED_LIMITS = {"any", "1h", "24h", "week", "month", "3months", "6months", "year"}

def _build_run_input(cfg: dict) -> dict:
    scraping = cfg.get("scraping", {})
    posted_limit = scraping.get("posted_limit", "month")
    if posted_limit not in _VALID_POSTED_LIMITS:
        log.warning(f"Invalid postedLimit '{posted_limit}', falling back to 'month'")
        posted_limit = "month"
    run_input = {
        "searchQueries": scraping.get("search_queries", ["marketing agency"]),
        "maxPostsPerQuery": scraping.get("max_posts_per_query", 50),
        "sortBy": scraping.get("sort_by", "date"),
        "postedLimit": posted_limit,
    }
    if scraping.get("author_industry_ids"):
        run_input["authorIndustryIds"] = [str(i) for i in scraping["author_industry_ids"]]
    if scraping.get("author_geo_ids"):
        run_input["authorGeoIds"] = [str(i) for i in scraping["author_geo_ids"]]
    return run_input


def _run_apify_sync(run_input: dict) -> list[dict]:
    from apify_client import ApifyClient
    client = ApifyClient(APIFY_API_TOKEN)
    actor_client = client.actor(APIFY_ACTOR_ID)
    run = actor_client.call(run_input=run_input, timeout_secs=600)
    dataset_client = client.dataset(run["defaultDatasetId"])
    return dataset_client.list_items().items


async def run_apify(emit, cfg: dict | None = None) -> list[dict]:
    if cfg is None:
        from admin_config import load
        cfg = load()

    scraping = cfg.get("scraping", {})
    run_input = _build_run_input(cfg)
    total_cap = scraping.get("total_post_cap", 500)
    min_len = cfg.get("filtering", {}).get("min_post_length", 50)

    await emit({"event": "stage_start", "stage": 1, "name": "Apify Scraper",
                "message": f"Scraping LinkedIn with {len(run_input['searchQueries'])} keywords..."})
    await emit({"event": "progress", "stage": 1, "message": "Apify run started, waiting for completion..."})

    try:
        posts = await asyncio.to_thread(_run_apify_sync, run_input)
    except Exception as e:
        err = str(e)
        if "actor" in err.lower() and "not found" in err.lower():
            raise RuntimeError("Invalid Apify actor ID in .env")
        raise RuntimeError(f"Apify scrape failed: {err}")

    if not posts:
        raise RuntimeError("Apify returned 0 results — no posts found for given search queries")

    # Filter empty content (HarvestAPI uses 'content' field, not 'text')
    from post_fields import get_content
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
