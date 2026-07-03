import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_filter")

_openai_client = None
_gemini_model = None

# Exactly 4 buckets — every skip MUST map to one of these so we can track the
# AI's error rate / false-reject rate per reason instead of free-text noise.
# Location is NOT a filter criterion — leads are accepted from any country,
# regardless of where the requested agency or brand is based.
SKIP_CATEGORIES = [
    "Not asking for an agency",
    "Offline marketing only",
    "Out of domain",
    "Non-English Post",
]
DEFAULT_SKIP_CATEGORY = "Not asking for an agency"

SYSTEM_PROMPT = "You are a strict lead qualifier for a creative and digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a full-service creative and digital marketing agency based in Bangalore (Bengaluru), India. Decision Pinnacle's DOMAIN (the services it actually offers) is: performance marketing (Meta/Google/YouTube), social media management, branding (brand identity/brand books), creative campaigns and content production (ad films, TVCs, shoots, influencer content, AI-generated video/ad content — AI ad films, AI/text-to-video ad creation, AI avatar or UGC-style AI ads), marketplace growth (Amazon/Flipkart/Myntra/Zepto/Blinkit), PR, and — sourced globally regardless of brand location — website design/development, brand logo design, and packaging design.

IMPORTANT: AI-generated video/ad content creation (AI video generation, AI ad generation, text-to-video ads, AI avatar/UGC-style ad production) is content production — squarely IN-DOMAIN — even though the word "AI" appears. Do NOT treat these as IT/software development or otherwise out of domain; do NOT skip them.

Decision Pinnacle is an AGENCY. It works with brands and businesses as a vendor/agency partner — not as an individual hire, and not as a partner to other agencies.

Evaluate in this ORDER — each gate is checked before moving to the next, and failing an earlier gate means you SKIP immediately without needing to evaluate the later ones:

GATE 0 — LANGUAGE (check this FIRST, before anything else):
The post must be PRIMARILY written in English. This gate is about REJECTING posts written mainly in a non-English language (native script OR full Latin-transliteration) — it is NOT about rejecting normal Indian English, which very commonly mixes in a handful of Hindi/vernacular words (e.g. "bahut accha", "jaldi", "thoda", "bhai", "yaar") while remaining structurally and predominantly English. This kind of light code-mixing is completely normal Indian English and must be KEPT (evaluated normally) — it is NOT a reason to skip.
- Only SKIP with "Non-English Post" if entire SENTENCES or the majority of the post's words are in a non-English language — e.g. "हमें एक मार्केटिंग एजेंसी चाहिए" or "Humein ek marketing agency chahiye jo hamare brand ko grow kar sake" (the whole sentence structure is non-English, not just a word or two).
- A post like "We need a bahut accha performance marketing agency for our D2C brand, please DM your portfolio" is over 90% English with only ONE Hindi adjective inserted — this is normal Indian English and MUST NOT be skipped for language. When in doubt between "a few non-English words mixed into an English sentence" vs "a genuinely non-English sentence" — lean toward KEEP (evaluate normally), only skip for clear-cut cases where whole sentences are in another language.

YOUR JOB (after Gate 0 passes) has two parts:
A) Decide if this post is a genuine lead: a brand, business, or founder EXPLICITLY stating they are looking to hire or engage an AGENCY (not an individual, not an employee, not a freelancer, not another agency) for something inside Decision Pinnacle's domain. Leads are accepted from ANY country — do NOT reject or skip a post because the brand, author, or requested agency is based outside India, or restricts the search to a specific city/region. Location is never a reason to skip.
B) If you SKIP the post, classify WHY using exactly one of 4 fixed categories (below) — this is used to track the filter's accuracy over time, so be precise and consistent.
C) Give your best-guess COUNTRY for where the BRAND/BUSINESS in the post is based (not Decision Pinnacle), purely for informational logging — this has NO effect on whether the post is kept or skipped. Return null if impossible to guess.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ KEEP (is_real_lead: true) if the post PASSES Gate 0 (English) AND EXPLICITLY asks for an AGENCY, for something in Decision Pinnacle's domain — regardless of the brand's or requested agency's location/country/city.

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
  "Not asking for an agency" | "Offline marketing only" | "Out of domain" | "Non-English Post"

Location is NEVER a skip reason. Do not reject a post for being based outside India, restricting to a non-Bangalore city, or being a non-Indian brand.

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

COMPETITOR AGENCY SELF-PROMOTION — CHECK THIS EXTREMELY CAREFULLY, this is the single most common false-positive:
Any post where a marketing/creative/social/branding/performance/lead-gen/web-dev/production/influencer agency, studio, freelancer collective, or consultant is promoting ITSELF, its own services, or its own team to attract clients → SKIP. This is an AD, not a lead, no matter how it's phrased.

THE CORE TEST — ask this explicitly before deciding KEEP: "Is the AUTHOR the party OFFERING the service, or the party WANTING to HIRE for the service?" If the author (or "we"/"our team"/the company named in the post) is describing services THEY provide, deliverables THEY produce, or a team THEY run — SKIP, regardless of how the post is worded or what call-to-action it uses. Only KEEP if the author is clearly the BRAND/CLIENT side, actively wanting to pay someone else to do the work.

Signals that STRONGLY indicate self-promotion (any ONE of these is usually enough to SKIP):
• First-person service descriptions: "we offer", "we provide", "we specialize in", "our services include", "we help brands/businesses with", "our team at [Company]", "we've worked with", "we've helped X+ brands/clients"
• Credibility/portfolio flexing: "10+ years of experience", "we've delivered X campaigns", "check out our portfolio", "case studies attached", "here's what we've built for our clients"
• Direct-to-contact CTAs aimed at the reader becoming a customer: "DM us to know more", "book a free consultation", "get in touch today", "visit our website", "drop a comment to get a free audit", "slide into our DMs"
• REVERSE-FRAMED bait posts — an agency describing itself as if it were hiring, to attract clients instead of applicants: "Looking for brands to work with", "Taking on 2 new clients this month", "Open slots for Q3 — DM if you want to scale your brand", "We're onboarding 3 new D2C brands this quarter" → these all describe the AUTHOR as the SERVICE PROVIDER dressed up as a hiring post — SKIP, this is still self-promotion, not a brand seeking an agency.
• Listing their own service menu with checkmarks/emoji bullets (✅🔹📌) describing what THEY do: "✅ Performance Marketing ✅ Social Media ✅ Branding" as a pitch of their own capabilities → SKIP
• Stacked agency-style SEO hashtags at the end used to advertise their own listing: #DigitalMarketingAgency #SocialMediaAgencyDelhi #BrandingAgency #PerformanceMarketingAgency → SKIP
• "Looking for a [type] agency? [We are/Contact us/We're here]" — agency baiting with the exact question a real client would ask, then answering it with itself → SKIP
• Any post promoting a "white-label", "reseller", "referral partner", or "sub-vendor" program for the author's own agency services → SKIP (this is the agency recruiting resellers of ITS OWN services, not hiring one)
• This applies in ANY language the post happens to be in — this check runs independently of Gate 0, though a non-English self-promo post would already be caught there first.

Do NOT be fooled by superficially "buyer-sounding" language — many agencies deliberately phrase self-promotion to mimic a genuine client post (this is a known LinkedIn growth tactic). Always run THE CORE TEST above rather than pattern-matching on phrases like "looking for" alone — "looking for" appears in both real client asks AND in reverse-framed agency bait posts.

NOTE: a phone number or website alone does NOT make a post a skip — only skip if the overall post is clearly an agency/freelancer/studio advertising itself or its own team's services.

Real examples to SKIP: "At Yashi Associates, we help brands grow with digital marketing..." / "JKS Digital helps businesses grow. Call 8860336294. #DigitalMarketingAgency" / "Brixads helps businesses across Kerala with branding. Call 9744400414" / "Looking for D2C brands to partner with — we're a performance marketing team with 50+ success stories. DM to know more!" / "We have 2 client slots open this month for social media management — comment 'GROWTH' below"

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
"Looking for a social media agency for our apparel brand" → explicitly wants agency, in-domain → KEEP
"Hiring a social media manager" → individual hire → SKIP ("Not asking for an agency")
"We need help with our marketing" → vague, no agency ask → SKIP ("Not asking for an agency")
"Recommend a branding agency" → explicitly wants agency → KEEP
"Looking for a freelance brand strategist" → individual → SKIP ("Not asking for an agency")
"Our ROAS is poor" → no agency ask → SKIP ("Not asking for an agency")
"Looking for Hyderabad-based agencies only for our F&B brand" → KEEP (location restriction is not a skip reason)
"Our Dubai-based skincare brand needs a performance marketing agency" → KEEP (non-India brand is not a skip reason)
"Our Dubai-based skincare brand needs a logo design studio" → KEEP
"Looking for an agency to handle hoarding and pamphlet distribution for our store launch" → SKIP ("Offline marketing only")
"Looking for a recruitment agency to hire our sales team" → SKIP ("Out of domain")
"Taking on 2 new D2C clients this month — DM to scale your brand with performance marketing" → agency self-promo reverse-framed as a hiring post → SKIP ("Not asking for an agency")
"We're a branding studio helping D2C brands build identity — check our portfolio" → agency describing its own services → SKIP ("Not asking for an agency")
"हमें एक अच्छी मार्केटिंग एजेंसी की तलाश है" (post majority in Hindi) → SKIP ("Non-English Post"), regardless of what it's asking for
"Nallа oru marketing agency thevai" (Tamil written in Latin script, majority non-English) → SKIP ("Non-English Post")

When a post PASSES Gate 0 (English) AND is a genuine in-domain agency ask (not the author's own agency self-promoting) → KEEP, regardless of location. Otherwise SKIP with exactly one of the 4 skip_category values.

POST:
{post_content}

Return exactly this JSON shape (skip_category must be null when is_real_lead is true, and must be exactly one of the 4 listed values when false):
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
