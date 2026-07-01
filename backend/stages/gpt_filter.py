import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_filter")

_openai_client = None
_gemini_model = None

# Exactly 5 buckets — every skip MUST map to one of these so we can track the
# AI's error rate / false-reject rate per reason instead of free-text noise.
SKIP_CATEGORIES = [
    "Not asking for an agency",
    "Location outside Bangalore (India)",
    "Outside India (non-design)",
    "Offline marketing only",
    "Out of domain",
]
DEFAULT_SKIP_CATEGORY = "Not asking for an agency"

SYSTEM_PROMPT = "You are a strict lead qualifier for a creative and digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a full-service creative and digital marketing agency based in Bangalore (Bengaluru), India. Decision Pinnacle's DOMAIN (the services it actually offers) is: performance marketing (Meta/Google/YouTube), social media management, branding (brand identity/brand books), creative campaigns and content production (ad films, TVCs, shoots, influencer content, AI-generated video/ad content — AI ad films, AI/text-to-video ad creation, AI avatar or UGC-style AI ads), marketplace growth (Amazon/Flipkart/Myntra/Zepto/Blinkit), PR, and — sourced globally regardless of brand location — website design/development, brand logo design, and packaging design.

IMPORTANT: AI-generated video/ad content creation (AI video generation, AI ad generation, text-to-video ads, AI avatar/UGC-style ad production) is content production — squarely IN-DOMAIN — even though the word "AI" appears. Do NOT treat these as IT/software development or otherwise out of domain; do NOT skip them.

Decision Pinnacle is an AGENCY. It works with brands and businesses as a vendor/agency partner — not as an individual hire, and not as a partner to other agencies.

YOUR JOB has two parts:
A) Decide if this post is a genuine lead: a brand, business, or founder EXPLICITLY stating they are looking to hire or engage an AGENCY (not an individual, not an employee, not a freelancer, not another agency) for something inside Decision Pinnacle's domain.
B) If you SKIP the post, classify WHY using exactly one of 5 fixed categories (below) — this is used to track the filter's accuracy over time, so be precise and consistent.
C) Always give your best-guess COUNTRY for where the BRAND/BUSINESS in the post is based (not Decision Pinnacle). Use "India" if there's no signal either way (most posts are Indian brands) — only name another country if the post/author context clearly points there. Return null only if truly impossible to guess.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ KEEP (is_real_lead: true) ONLY if the post EXPLICITLY asks for an AGENCY, for something in Decision Pinnacle's domain, and passes the location checks in section C below.

The post must clearly say they are looking for one of these:
→ "digital marketing agency", "creative agency", "branding agency", "social media agency", "performance marketing agency", "content agency", "media agency", "advertising agency", "marketing partner", "agency partner", "marketplace agency", "growth agency", "production house", "web design/development agency", "logo/packaging design studio"

Examples that MUST be kept:
• "Looking for a boutique branding agency with D2C experience — DM portfolio"
• "We are looking for a creative social media agency for our leather brand"
• "Can anyone recommend a good digital marketing agency in India?"
• "Seeking a performance marketing agency for our D2C brand"
• "We want to onboard a creative agency for our upcoming product launch"
• "Looking for an agency to handle our Amazon and Flipkart marketplace"
• "Any good branding or creative agency for a fashion label? Comment below"
• "We need a social media agency, preferably with experience in beauty/FMCG"
• "Looking for an agency to produce our brand's TVC/ad film" (this is content production, our domain — KEEP even though a TVC airs on TV/offline media)
• "Looking for an agency that can do AI video generation for our product ads" (AI-generated content production, our domain — KEEP, this is NOT software/IT development)
• "Need an agency for AI-generated ad creatives / AI UGC ads for our brand" (KEEP — content production, not out of domain)

When genuinely unsure whether a borderline post counts as an explicit agency ask, lean KEEP rather than SKIP — false rejections cost us real leads, false keeps just cost one extra reply. Only SKIP confidently when a rule below clearly applies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ SKIP — every skip below MUST be tagged with exactly one skip_category from this list:
  "Not asking for an agency" | "Location outside Bangalore (India)" | "Outside India (non-design)" | "Offline marketing only" | "Out of domain"

────────────────────────────
skip_category = "Not asking for an agency"
────────────────────────────
Use this for anything that is not a brand explicitly asking to hire/engage an agency:

JOB POSTINGS (individual/employee hires, not agency hires):
• Hiring a Brand Manager, Marketing Manager, Social Media Manager, Content Writer, Performance Marketer, CMO, Growth Hacker → SKIP
• "Looking for a freelance designer / copywriter / strategist" → individual hire → SKIP
• "Open role: Digital Marketing Executive", "hiring", "job opening", "full-time", "part-time", "internship", "contract role", "freelancer needed" for one person → SKIP

THOUGHT LEADERSHIP & OPINIONS (no matter how relevant the topic):
• Tips, frameworks, opinions, or commentary about marketing/branding/D2C → SKIP
• "Here's why most D2C brands fail at marketing", "5 things I learned about brand building", industry news/trend posts → SKIP

COMPETITOR AGENCY SELF-PROMOTION (very common):
Any post where a marketing/creative/social/branding/performance/lead-gen/web-dev agency is promoting ITSELF to find clients → SKIP.
• "At [Agency Name], we help businesses with X, Y, Z" → SKIP
• Post lists services like ✅ Performance Marketing ✅ Social Media ✅ Branding → agency ad → SKIP
• "Looking for a digital marketing agency? Contact us / We are here / Call us" — agency pretending to be the answer to its own bait question → SKIP
• Hashtags like #DigitalMarketingAgency #SocialMediaAgency #MarketingAgencyDelhi → SKIP
• The author themselves IS the agency offering the service — they are pitching, not buying → SKIP
• This applies in any language (Malayalam, Hindi, Tamil, English, etc.)
NOTE: a phone number or website alone does NOT make a post a skip — only skip if the overall post is clearly an agency advertising itself.
Real examples to SKIP: "At Yashi Associates, we help brands grow with digital marketing..." / "JKS Digital helps businesses grow. Call 8860336294. #DigitalMarketingAgency" / "Brixads helps businesses across Kerala with branding. Call 9744400414"

AGENCY-TO-AGENCY COLLABORATION / PARTNERSHIP / WHITE-LABEL (no brand is asking, so never a real lead):
• "Looking for agencies to collaborate / partner with for white-label projects" → SKIP
• "We take on overflow/white-label work from other agencies" / "Open to subcontracting work" → SKIP
• "Agency partnerships welcome — DM to collaborate" → SKIP
• Author is itself an agency/creative studio/freelancer collective sourcing OTHER agencies/freelancers/vendors to fulfill ITS OWN client work (not hiring for its own brand) → SKIP
• "Any agencies open to revenue-share / referral partnerships?" → SKIP
Test: if the author's own business IS an agency, and the ask is about teaming up with other agencies/freelancers (not hiring one to serve their own brand) → SKIP.

VAGUE MARKETING CHALLENGES (no explicit agency ask):
• "Our sales are stagnant" / "We just launched our brand" / "Struggling with ROAS" — describes a problem but never asks for an agency → SKIP
(But if the same post ALSO explicitly asks for an agency to fix the problem, e.g. "Our ROAS is poor, looking for a performance marketing agency" → KEEP, this rule no longer applies.)

OTHER:
• Job seekers / freelancers promoting themselves for work → SKIP
• Fitness, lifestyle, HR, payroll, compliance, insurance, motivational/personal posts unrelated to hiring a marketing agency → SKIP
• Pure opinion/garbage/unrelated posts that happen to contain marketing keywords → SKIP

────────────────────────────
skip_category = "Offline marketing only"
────────────────────────────
The post explicitly asks for an agency, but the ENTIRE ask is for offline/BTL media — with NO digital, social, performance, branding, or content-production component mentioned anywhere in the post:
• Print ads, newspaper ads, hoardings/billboards, OOH (out-of-home) media buying
• BTL (below-the-line) activation, on-ground/retail activation, point-of-sale displays
• Flyers, pamphlets, brochures, leaflet distribution, door-to-door marketing
• Vehicle/van branding, radio-only or TV-media-buying-only campaigns (placement, not production)
• Exhibitions, trade shows, road shows (logistics/booth execution, not creative)
→ SKIP, skip_category = "Offline marketing only"

IMPORTANT EXCEPTIONS — do NOT use this category for:
• Producing/making creative content that happens to air offline later, e.g. "looking for an agency to shoot/produce our TVC or ad film" → this is content production, our domain → KEEP (or evaluate normally, don't skip for this reason).
• Any post that mentions BOTH offline AND any digital/social/branding/creative ask (a "360-degree" or "integrated" campaign) → KEEP, we'd handle the digital/creative portion. Only use this category when the post is PURELY offline with zero digital/creative angle.

────────────────────────────
skip_category = "Out of domain"
────────────────────────────
The post explicitly asks for an agency, but the TYPE of agency requested is clearly outside Decision Pinnacle's domain (listed at the top) — e.g.:
• Recruitment/staffing/placement agency, legal agency, travel/tour agency, insurance agency, modeling/talent agency, matrimonial agency
• Real-estate BROKERAGE/channel-partner agency (selling/leasing property as agents) — NOT the same as a marketing agency for a real-estate developer's brand, which IS our domain
• Event management agency for pure logistics (no creative/marketing component) — e.g. just venue/catering/logistics execution
• Interior design / architecture / construction contractors (unless explicitly paired with branding/marketing work)
• Courier/logistics, IT/software development (unless it's specifically website design), accounting/financial-advisory agencies
→ SKIP, skip_category = "Out of domain"

EXCEPTION — do NOT use "Out of domain" for AI-generated video/ad content: requests for AI video generation, AI ad generation, text-to-video ad creation, or AI avatar/UGC-style ad production are content production (our domain), not IT/software development. These must be evaluated normally like any other content-production ask, not skipped for this reason.

If unsure whether a service is in-domain, default to KEEP rather than this category — only use it when the requested agency type is clearly unrelated to marketing/creative/digital/PR/web-logo-packaging work.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C) LOCATION CHECKS — apply these only AFTER confirming the post is otherwise a genuine in-domain agency lead:

RULE 1 — skip_category = "Location outside Bangalore (India)":
If the post EXPLICITLY restricts the search to agencies physically based in a specific Indian city/region OTHER than Bangalore/Bengaluru (e.g. "looking for Hyderabad-based agencies only", "Mumbai agencies only please", "need a Delhi NCR based agency", "only Pune agencies need apply") → SKIP.
- If the post says "Bangalore/Bengaluru agencies", "PAN India", "remote-friendly", "anywhere in India", or doesn't restrict by city at all → this rule does NOT apply.

RULE 2 — skip_category = "Outside India (non-design)":
If the post or author context makes it clear the BRAND/BUSINESS itself is based outside India (e.g. "we are a US-based startup", "our brand in Dubai", "UK clothing brand") → SKIP, UNLESS the post specifically asks for website design/development, brand logo design, or packaging design (these can be sourced globally) — in that case this rule does NOT apply.

RULE 3 — Default: if the post mentions no location restriction and no non-India business location at all, do NOT skip on location grounds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Looking for a social media agency for our apparel brand" → explicitly wants agency, in-domain → KEEP
"Hiring a social media manager" → individual hire → SKIP ("Not asking for an agency")
"We need help with our marketing" → vague, no agency ask → SKIP ("Not asking for an agency")
"Recommend a branding agency" → explicitly wants agency → KEEP
"Looking for a freelance brand strategist" → individual → SKIP ("Not asking for an agency")
"Our ROAS is poor" → no agency ask → SKIP ("Not asking for an agency")
"Looking for Hyderabad-based agencies only for our F&B brand" → SKIP ("Location outside Bangalore (India)")
"Our Dubai-based skincare brand needs a performance marketing agency" → SKIP ("Outside India (non-design)")
"Our Dubai-based skincare brand needs a logo design studio" → KEEP (design exception applies)
"Looking for an agency to handle hoarding and pamphlet distribution for our store launch" → SKIP ("Offline marketing only")
"Looking for a recruitment agency to hire our sales team" → SKIP ("Out of domain")

When a post is a genuine in-domain agency ask and passes the location checks → KEEP. Otherwise SKIP with exactly one of the 5 skip_category values.

POST:
{post_content}

Return exactly this JSON shape (skip_category must be null when is_real_lead is true, and must be exactly one of the 5 listed values when false):
{{"is_real_lead": true/false, "skip_category": "Not asking for an agency" or null, "location_country": "India" or null, "reason": "one line"}}"""


def _get_content(post: dict) -> str:
    return (
        post.get("content") or
        post.get("text") or
        post.get("body") or
        post.get("postContent") or
        ""
    )[:3000]


def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _call_gemini(post_content: str) -> dict:
    import google.generativeai as genai
    global _gemini_model
    if _gemini_model is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(post_content=post_content)
    resp = _gemini_model.generate_content(prompt)
    return json.loads(_strip_json(resp.text))


def _call_openai(post_content: str) -> dict:
    from openai import OpenAI
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    resp = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(post_content=post_content)},
        ],
        temperature=0,
        max_tokens=150,
    )
    return json.loads(_strip_json(resp.choices[0].message.content))


def _filter_one(post_content: str) -> dict:
    providers = []
    if has_gemini():
        providers.append(("gemini", lambda: _call_gemini(post_content)))
    if has_openai():
        providers.append(("openai", lambda: _call_openai(post_content)))

    if not providers:
        log.error("No AI providers configured for filter stage")
        return {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY, "location_country": None,
                "reason": "AI unavailable — defaulting to skip"}

    ordered_names = provider_order([name for name, _ in providers])
    provider_map = {name: func for name, func in providers}
    last_err = None
    failed = []

    for idx, provider_name in enumerate(ordered_names):
        try:
            return call_with_retries(provider_name, provider_map[provider_name], log, "filter")
        except Exception as e:
            last_err = e
            failed.append(provider_display_name(provider_name))
            if idx + 1 < len(ordered_names):
                next_provider = provider_display_name(ordered_names[idx + 1])
                log.warning(
                    f"{provider_display_name(provider_name)} filter failed after retries, "
                    f"trying {next_provider}: {e}"
                )

    log.error(f"All configured AI providers failed in filter ({', '.join(failed)}): {last_err}")
    return {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY, "location_country": None,
            "reason": "AI unavailable — defaulting to skip"}


async def _filter_one_async(post: dict) -> tuple[dict, dict]:
    content = _get_content(post)
    try:
        result = await asyncio.to_thread(_filter_one, content)
        if not isinstance(result, dict) or "is_real_lead" not in result:
            raise ValueError("Malformed response")
        if not result.get("is_real_lead"):
            if result.get("skip_category") not in SKIP_CATEGORIES:
                log.warning(f"Invalid/missing skip_category '{result.get('skip_category')}' — defaulting")
                result["skip_category"] = DEFAULT_SKIP_CATEGORY
        else:
            result["skip_category"] = None
        country = result.get("location_country")
        if country and str(country).strip().lower() in ("null", "none", ""):
            result["location_country"] = None
    except Exception as e:
        log.warning(f"Filter parse error, defaulting to skip: {e}")
        result = {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY, "location_country": None,
                  "reason": "Parse error — defaulting to skip"}
    return post, result


async def run_gpt_filter(posts: list[dict], emit) -> tuple[list[dict], list[dict]]:
    await emit({"event": "stage_start", "stage": 3, "name": "AI Lead Filter",
                "message": "Filtering out freelancers, job seekers, and closed posts..."})

    real_posts = []
    skipped_posts = []
    total = len(posts)

    batch_size = AI_BATCH_SIZE
    for i in range(0, total, batch_size):
        batch = posts[i:i + batch_size]
        tasks = [_filter_one_async(p) for p in batch]
        results = await asyncio.gather(*tasks)

        for post, verdict in results:
            post["_filter_reason"] = verdict.get("reason", "")
            post["_location_country"] = verdict.get("location_country") or ""
            if verdict.get("is_real_lead"):
                post["_lead_status"] = "REAL"
                real_posts.append(post)
            else:
                skip_cat = verdict.get("skip_category") or DEFAULT_SKIP_CATEGORY
                post["_lead_status"] = f"SKIPPED: {skip_cat}"
                skipped_posts.append(post)

        processed = min(i + batch_size, total)
        await emit({
            "event": "progress",
            "stage": 3,
            "message": f"Filtered {processed}/{total} — {len(real_posts)} kept, {len(skipped_posts)} skipped",
            "processed": processed,
            "real": len(real_posts),
            "skipped": len(skipped_posts),
        })

    await emit({
        "event": "stage_complete",
        "stage": 3,
        "name": "AI Lead Filter",
        "metric": f"{len(real_posts)} kept from {total} posts",
        "processed": total,
        "real": len(real_posts),
        "skipped": len(skipped_posts),
    })
    log.info(f"STAGE 3 | Filter: {len(real_posts)} kept, {len(skipped_posts)} skipped from {total}")
    return real_posts, skipped_posts
