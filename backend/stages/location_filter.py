from logger import get_logger
from post_fields import get_author_headline, get_content

log = get_logger("location_filter")

# Runs AFTER the AI lead filter (Stage 3) — only re-checks posts the AI
# already accepted as genuine leads. Posts that fail are moved to skipped
# under "Skipped based on location" instead of being dropped before the AI
# filter ever sees them; everything goes through Stage 3 first.

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

_REASON_LABELS = {
    "no India signal": "No India Signal",
    "agency author": "Agency Author",
}


def _check_one(post: dict) -> tuple[bool, str]:
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


def apply_location_filter(real_posts: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Re-checks posts the AI filter already marked real. Returns
    (still_real, rejected, stats). Rejected posts are tagged with
    _lead_status so they show up in the sheet as skipped, not dropped."""
    passed = []
    rejected = []
    reasons = {"no India signal": 0, "agency author": 0}
    for post in real_posts:
        ok, reason = _check_one(post)
        if ok:
            passed.append(post)
        else:
            reasons[reason] += 1
            post["_lead_status"] = f"SKIPPED: Location outside India - {_REASON_LABELS[reason]}"
            post["_filter_reason"] = reason
            rejected.append(post)
    stats = {
        "total": len(real_posts),
        "passed": len(passed),
        "rejected_no_india": reasons["no India signal"],
        "rejected_agency": reasons["agency author"],
    }
    return passed, rejected, stats
