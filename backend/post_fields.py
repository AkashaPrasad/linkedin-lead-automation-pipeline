"""
Centralised helpers for extracting fields from Apify LinkedIn post objects.

Two actors feed this pipeline (selected via scraping.use_cookie_actor) with
different output shapes, so every getter below checks both:

HarvestAPI (harvestapi/linkedin-post-search, no cookies):
  post.content        — post text (NOT post.text which is empty)
  post.shareLinkedinUrl — post URL
  post.linkedinUrl    — also post URL (fallback)
  post.postedAt       — ISO timestamp
  post.author.name        — full name
  post.author.linkedinUrl — profile URL (NOT author.url which is absent)
  post.author.info        — headline / title string (NOT author.headline)

curious_coder/linkedin-post-search-scraper (cookie-authenticated):
  post.text               — post text
  post.url                — post URL
  post.authorFullName     — full name (flat, not nested under author)
  post.authorProfileUrl   — profile URL (flat)
  post.authorHeadline     — headline (flat)
  post.postedAtISO        — ISO timestamp (NOT post.postedAt, which is absent)
  post.postedAtTimestamp  — epoch milliseconds (fallback if ISO is missing)
"""


def get_content(post: dict) -> str:
    return (
        post.get("content") or
        post.get("text") or
        post.get("body") or
        post.get("postContent") or
        ""
    )


def get_post_url(post: dict) -> str:
    return (
        post.get("shareLinkedinUrl") or
        post.get("linkedinUrl") or
        post.get("url") or
        post.get("postUrl") or
        ""
    )


def get_author_url(post: dict) -> str:
    author = post.get("author") or {}
    return (
        author.get("linkedinUrl") or
        author.get("url") or
        author.get("profileUrl") or
        post.get("authorProfileUrl") or
        ""
    ).strip()


def get_author_name(post: dict) -> str:
    author = post.get("author") or {}
    return (
        author.get("name") or
        author.get("fullName") or
        post.get("authorFullName") or
        ""
    ).strip()


def get_author_headline(post: dict) -> str:
    author = post.get("author") or {}
    # HarvestAPI puts the headline in author.info (string)
    info = author.get("info") or ""
    if isinstance(info, dict):
        info = info.get("title") or info.get("headline") or ""
    return (
        author.get("headline") or
        author.get("title") or
        str(info) or
        post.get("authorHeadline") or
        ""
    ).strip()


def get_posted_date(post: dict) -> str:
    iso = post.get("postedAt") or post.get("postedDate") or post.get("postedAtISO")
    if iso:
        return str(iso)
    ts = post.get("postedAtTimestamp")
    if ts:
        try:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except Exception:
            return str(ts)
    return ""
