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
