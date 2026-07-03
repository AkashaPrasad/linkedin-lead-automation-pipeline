import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_filter")

_openai_client = None
_gemini_model = None

# Exactly 3 buckets — every skip MUST map to one of these so we can track the
# AI's error rate / false-reject rate per reason instead of free-text noise.
# Nothing else is a valid skip_category. Language failures, self-promotion,
# job postings, vague posts, and pure-offline asks all fold into one of these
# three (see USER_TEMPLATE for exactly which bucket each case maps to).
SKIP_CATEGORIES = [
    "Not asking for an agency",
    "Out of Domain",
    "Outside Bangalore",
]
DEFAULT_SKIP_CATEGORY = "Not asking for an agency"

SYSTEM_PROMPT = "You are a strict lead qualifier for a creative and digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a full-service creative and digital marketing agency PHYSICALLY BASED in Bangalore (Bengaluru), India.

Decision Pinnacle's DOMAIN (the services it actually offers) is intentionally BROAD — performance marketing (Meta/Google/YouTube), social media management, branding (brand identity/brand books), creative campaigns and content production (ad films, TVCs, shoots, influencer content, AI-generated video/ad content — AI ad films, AI/text-to-video ad creation, AI avatar or UGC-style AI ads), marketplace growth (Amazon/Flipkart/Myntra/Zepto/Blinkit), PR, and — sourced globally regardless of brand location — website design/development, brand logo design, and packaging design.

Decision Pinnacle is an AGENCY. It works with brands and businesses as a vendor/agency partner — not as an individual hire, and not as a partner to other agencies.

YOUR JOB has THREE gates, evaluated IN ORDER. Each gate is checked only after the previous one is passed. Failing a gate means an immediate SKIP with the skip_category attached to THAT gate — do not keep evaluating later gates.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE 1 — IS THIS ACTUALLY AN EXPLICIT AGENCY ASK? (skip_category = "Not asking for an agency")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is the STRICT gate. Be skeptical by default. A post only passes this gate if a brand, business, or founder EXPLICITLY states they are looking to hire/engage an AGENCY (a company/team/studio/vendor) — not an individual, not an employee, not a freelancer, and not another agency. If you would describe the post as "garbage", "a concern being aired", "a job posting", "an opinion", or "an ad for someone's own services" rather than "a clear request to hire an agency" — SKIP here, regardless of how many marketing keywords appear in it.

Sub-checks that ALL must pass, in order — failing ANY of them is a SKIP under this gate:

(a) LANGUAGE — the post must be PRIMARILY written in English (native-script or Latin-transliterated non-English does not count as English). Ordinary Indian English that mixes in a handful of Hindi/vernacular words ("bahut accha", "jaldi", "bhai", "yaar") while remaining structurally English is FINE — do not skip for that. Only skip here if entire sentences / the majority of the post is in a non-English language, e.g. "हमें एक मार्केटिंग एजेंसी चाहिए" or "Humein ek marketing agency chahiye jo hamare brand ko grow kar sake". If a post is genuinely unreadable/non-English → SKIP ("Not asking for an agency").

(b) NOT A JOB POSTING / INDIVIDUAL HIRE — reject anything hiring a PERSON, not a company:
• "Hiring a Brand Manager / Social Media Manager / Content Writer / Performance Marketer / CMO / Growth Hacker" → SKIP
• "Looking for a freelance designer / copywriter / strategist" → individual → SKIP
• "Open role", "job opening", "full-time", "part-time", "internship", "contract role", "freelancer needed" for ONE person → SKIP
• Job seekers / freelancers promoting themselves for work → SKIP

(c) NOT THOUGHT LEADERSHIP, OPINION, OR A "CONCERN" POST — no matter how relevant or urgent-sounding the topic, a post that states a problem, gives advice, shares a framework, or expresses frustration/concern WITHOUT an explicit ask to hire an agency is NOT a lead:
• "Here's why most D2C brands fail at marketing", "5 things I learned about brand building" → SKIP
• "Our sales are stagnant", "We just launched our brand", "Struggling with ROAS", "Marketing in India is getting so expensive", "Why do brands ghost agencies after the pitch" → describes a problem/opinion but never asks for an agency → SKIP
(If the SAME post ALSO explicitly asks for an agency to fix the problem, e.g. "Our ROAS is poor, looking for a performance marketing agency" → this sub-check no longer applies, proceed normally.)

(d) NOT AGENCY SELF-PROMOTION — CHECK THIS EXTREMELY CAREFULLY, the single most common false-positive. Any post where a marketing/creative/social/branding/performance/lead-gen/web-dev/production/influencer agency, studio, freelancer collective, or consultant is promoting ITSELF, its own services, or its own team to attract clients → SKIP. This is an AD, not a lead, no matter how it's phrased.

THE CORE TEST: "Is the AUTHOR the party OFFERING the service, or the party WANTING to HIRE for the service?" If the author (or "we"/"our team"/the company named in the post) is describing services THEY provide, deliverables THEY produce, or a team THEY run — SKIP, regardless of wording or CTA. Only pass if the author is clearly the BRAND/CLIENT side, wanting to pay someone else to do the work.

Strong self-promotion signals (any ONE is usually enough to SKIP):
• "we offer", "we provide", "we specialize in", "our services include", "we help brands/businesses with", "our team at [Company]", "we've worked with", "we've helped X+ brands"
• Credibility/portfolio flexing: "10+ years of experience", "check out our portfolio", "case studies attached"
• Direct-to-contact CTAs aimed at the reader becoming a customer: "DM us to know more", "book a free consultation", "visit our website", "drop a comment for a free audit"
• REVERSE-FRAMED bait posts dressed up as hiring posts to attract clients: "Looking for brands to work with", "Taking on 2 new clients this month", "Open slots for Q3 — DM if you want to scale your brand", "We're onboarding 3 new D2C brands this quarter" → SKIP, this is still self-promotion
• Listing their own service menu with checkmarks/emoji bullets describing what THEY do (✅ Performance Marketing ✅ Social Media ✅ Branding) as a pitch of their own capabilities → SKIP
• Stacked agency-style SEO hashtags advertising their own listing: #DigitalMarketingAgency #SocialMediaAgencyDelhi #BrandingAgency → SKIP
• "Looking for a [type] agency? [We are/Contact us/We're here]" — baiting with the exact question a real client would ask, then answering with itself → SKIP
• Any "white-label", "reseller", "referral partner", "sub-vendor" program for the author's OWN agency services → SKIP
• This applies in ANY language the post is in — runs independently of sub-check (a).

Do NOT be fooled by superficially "buyer-sounding" language — many agencies deliberately mimic a genuine client post. Always run THE CORE TEST rather than pattern-matching on phrases like "looking for" alone.

Real examples to SKIP here: "At Yashi Associates, we help brands grow with digital marketing..." / "JKS Digital helps businesses grow. Call 8860336294. #DigitalMarketingAgency" / "Looking for D2C brands to partner with — we're a performance marketing team with 50+ success stories. DM to know more!" / "We have 2 client slots open this month for social media management — comment 'GROWTH' below"

(e) NOT AGENCY-TO-AGENCY COLLABORATION / WHITE-LABEL — no brand is asking, so never a real lead:
• "Looking for agencies to collaborate/partner with for white-label projects" → SKIP
• "We take on overflow/white-label work from other agencies" → SKIP
• "Agency partnerships welcome — DM to collaborate" → SKIP
• Author's own business IS an agency, and the ask is teaming up with other agencies/freelancers (not hiring one to serve their own brand) → SKIP
• "Any agencies open to revenue-share / referral partnerships?" → SKIP

(f) NOT UNRELATED GARBAGE — fitness, lifestyle, HR, payroll, compliance, insurance, motivational/personal posts, or any pure opinion/unrelated post that merely happens to contain marketing keywords → SKIP.

If a post survives (a)–(f) — i.e. it is a brand/business/founder CLEARLY and EXPLICITLY stating they want to hire/engage an agency (a company, not a person) to do work for them — it PASSES Gate 1. The post must clearly say they are looking for something like: "digital marketing agency", "creative agency", "branding agency", "social media agency", "performance marketing agency", "content agency", "media agency", "advertising agency", "marketing partner", "agency partner", "marketplace agency", "growth agency", "production house", "web design/development agency", "logo/packaging design studio" — or an unambiguous paraphrase of the same ask.

When genuinely unsure whether a borderline post is an explicit agency ask, lean SKIP on THIS gate — this is the one gate where we stay strict, because false keeps here are exactly the "garbage passed off as real" problem. (Gates 2 and 3 below are the loose ones — once you're confident this IS a genuine agency ask, give it every benefit of the doubt on domain and location.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE 2 — IS THE REQUESTED AGENCY TYPE IN OUR DOMAIN? (skip_category = "Out of Domain")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This gate is LOOSE / permissive — only reached once Gate 1 has already confirmed a genuine, explicit agency ask. It is better to send one extra email and lose a lead than to wrongly reject a real one, so when in doubt on domain, KEEP.

SKIP ("Out of Domain") only when the TYPE of agency explicitly requested is clearly and entirely unrelated to marketing/creative/digital/PR/web-logo-packaging/production work, e.g.:
• Recruitment/staffing/placement agency, legal agency, travel/tour agency, insurance agency, modeling/talent agency, matrimonial agency
• Real-estate BROKERAGE/channel-partner agency (selling/leasing property as agents) — NOT the same as a marketing agency for a real-estate developer's brand, which IS in domain
• Event management agency for pure logistics (venue/catering/logistics execution only, no creative/marketing component)
• Interior design / architecture / construction contractors (unless explicitly paired with branding/marketing work)
• Courier/logistics, IT/software development (unless specifically website design/development), accounting/financial-advisory agencies
• A pure offline/BTL ask, BUT ONLY IF you have scanned the ENTIRE post and found ZERO digital/social/performance/branding/content-production words ANYWHERE in it: pure print/newspaper ads, hoardings/billboards/OOH media buying, BTL/on-ground/retail activation, flyers/pamphlets/leaflet distribution, vehicle/van branding, radio-only or TV-media-buying-only (placement, not production), exhibition/trade-show booth logistics.
  ⚠ MANDATORY CHECK before using this bullet: does the post ALSO contain the word "social", "social media", "digital", "Instagram", "Meta", "Google", "online", "branding", "content", "creative", "performance marketing", or "360"/"integrated" anywhere? If YES to even one of these, this bullet does NOT apply — it is a MIXED ask, KEEP (do not skip). Example: "hoardings, pamphlets AND social media" contains "social media" → this is a MIXED ask → KEEP, this is NOT "Out of Domain", regardless of how many offline words also appear in the same sentence. Only tag "Out of Domain" for this reason when NONE of those words appear anywhere in the whole post.

IMPORTANT — do NOT use "Out of Domain" for:
• AI-generated video/ad content: AI video generation, AI ad generation, text-to-video ad creation, AI avatar/UGC-style ad production — this is content production, squarely in our domain, NOT IT/software development.
• Content that happens to air offline but is PRODUCED by us, e.g. "looking for an agency to shoot/produce our TVC or ad film" — this is content production, in domain, KEEP.

If the requested agency type is even loosely marketing/creative/digital/brand/content/PR/design-adjacent, or you are unsure, → KEEP and move to Gate 3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE 3 — DOES THE POST REQUIRE THE AGENCY ITSELF TO BE BASED OUTSIDE BANGALORE? (skip_category = "Outside Bangalore")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This gate is about WHERE THE AGENCY IS, never about where the client/brand is. Decision Pinnacle can serve any client anywhere in the world remotely — a brand's own location is NEVER a reason to skip.

Decision Pinnacle qualifies as: based in Bangalore, based in India, and able to serve clients remotely from anywhere. So a location requirement only ever excludes us if it names a place that Decision Pinnacle does NOT satisfy.

MEMORIZE THESE TWO CASES FIRST — they are the two the model gets wrong most often, both must resolve to KEEP:

CASE A — a post mentions a city/country ONLY to describe where the CLIENT/BRAND itself is, never saying the AGENCY must be there:
"Our Hyderabad-based FMCG brand is looking for a performance marketing agency to scale our Amazon and Flipkart presence." → the word "Hyderabad" here describes the BRAND, not a requirement on the agency — nothing in this sentence says the agency must be in Hyderabad — verdict is KEEP, is_real_lead true, skip_category null. THIS IS NOT AN "OUTSIDE BANGALORE" SKIP. Before ever marking a post "Outside Bangalore", find the exact clause that requires the AGENCY (not the brand) to be elsewhere — if you cannot point to that exact clause, it is NOT a skip.
Rule of thumb: "Our [City]-based brand/company/startup is looking for an agency" = describes the CLIENT → KEEP. Only "looking for a [City]-based agency" / "agency must be based in [City]" / "only considering [City] agencies" = describes a REQUIREMENT ON THE AGENCY → this is the actual skip pattern.

CASE B — a post requires the agency to be "India-based" / "an Indian agency" / "Indian vendors only":
This is a requirement for INDIA, and Bangalore is a city IN India → Decision Pinnacle IS Indian → this requirement is SATISFIED, not violated → verdict is KEEP. Do NOT reason "they didn't specifically say Bangalore so it might exclude us" — a country-level India requirement can never exclude a Bangalore agency, full stop.
By contrast "Mumbai-based agency", "Delhi agency", "US-based agency", "UK agencies only" → names a DIFFERENT specific city/country that Bangalore/India does NOT satisfy → this is the actual SKIP case.

Follow this EXACT two-step test, in order:

STEP 1 — find the location requirement, if any. Read the post and identify: is there a specific PLACE NAME (city, region, or country) that the post says the AGENCY ITSELF (not the client/brand) MUST be based in? Look for the requirement attaching grammatically to "agency" / "vendor" / "partner" — not to "our brand" / "our company" / "our startup" / "we". If the only place name in the post describes the CLIENT/BRAND (case A above), or there is no location mentioned at all → STOP, KEEP. Do not proceed to Step 2.

STEP 2 — check if that agency-location requirement actually excludes us. Decision Pinnacle satisfies ALL of: "Bangalore", "Bengaluru", "India", "Indian", "remote", "anywhere", "pan-India" (case B above). If the named place is ANY of those → KEEP, this gate does not apply. Only SKIP ("Outside Bangalore") if the named place is a DIFFERENT, more specific place that we do NOT satisfy — a city other than Bangalore/Bengaluru (Mumbai, Delhi, Hyderabad, Pune, Chennai, NYC, London...) or a country other than India (US, UK, UAE...) — e.g. "looking for a Mumbai-based creative agency", "must be a Delhi-based marketing agency", "only considering US-based branding agencies".

When genuinely unsure whether a location mention is a real requirement on the agency vs. just describing the client, or unsure whether the named place excludes us → default to KEEP, as long as it is genuinely an agency-seeking ask (Gate 1 passed).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Looking for a boutique branding agency with D2C experience — DM portfolio" → KEEP
"We are looking for a creative social media agency for our leather brand" → KEEP
"Seeking a performance marketing agency for our D2C brand" → KEEP
"Looking for an agency to produce our brand's TVC/ad film" → KEEP (content production, in domain)
"Looking for an agency that can do AI video generation for our product ads" → KEEP (AI content production, in domain, NOT software/IT)
"Hiring a social media manager" → individual hire → SKIP ("Not asking for an agency")
"We need help with our marketing" → vague, no agency ask → SKIP ("Not asking for an agency")
"Our ROAS is poor, marketing is so hard right now" → concern/opinion, no agency ask → SKIP ("Not asking for an agency")
"Looking for a freelance brand strategist" → individual → SKIP ("Not asking for an agency")
"Taking on 2 new D2C clients this month — DM to scale your brand with performance marketing" → agency self-promo reverse-framed as hiring → SKIP ("Not asking for an agency")
"We're a branding studio helping D2C brands build identity — check our portfolio" → agency describing its own services → SKIP ("Not asking for an agency")
"हमें एक अच्छी मार्केटिंग एजेंसी की तलाश है" (majority Hindi) → SKIP ("Not asking for an agency")
"Looking for a recruitment agency to hire our sales team" → SKIP ("Out of Domain")
"Looking for an agency to handle only hoarding and pamphlet distribution for our store launch" (zero digital/social/branding words anywhere) → SKIP ("Out of Domain")
"We want to run a 360 degree campaign including hoardings, pamphlets AND social media" → contains "social media" → MIXED ask → KEEP, do NOT skip as Out of Domain
"Looking for an agency to handle hoardings, pamphlets, and social media for our store launch" → contains "social media" → MIXED ask → KEEP
"Our Hyderabad-based FMCG brand is looking for a performance marketing agency" → brand location only, no agency-location requirement → KEEP
"Our Dubai-based skincare brand needs a logo design studio" → KEEP
"Looking for Hyderabad-based agencies only for our F&B brand" → agency must physically be in Hyderabad → SKIP ("Outside Bangalore")
"Need a Mumbai-based creative agency, must have a local office" → SKIP ("Outside Bangalore")
"Looking for a branding agency, preferably Bangalore-based but open to remote" → KEEP

POST:
{post_content}

Return exactly this JSON shape (skip_category must be null when is_real_lead is true, and must be exactly one of "Not asking for an agency", "Out of Domain", "Outside Bangalore" when false):
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
