import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_filter")

_openai_client = None
_gemini_model = None

# Exactly 2 buckets — every skip MUST map to one of these so we can track the
# AI's error rate / false-reject rate per reason instead of free-text noise.
# Nothing else is a valid skip_category. Non-English posts, self-promotion,
# job postings, and vague posts all fold into one of these two (see
# USER_TEMPLATE for exactly which bucket each case maps to). Location is NOT
# a skip reason at all — country/location filtering happens once, at scrape
# time (Apify's authorGeoIds = India), never here.
SKIP_CATEGORIES = [
    "Not asking for an agency",
    "Out of Domain",
]
DEFAULT_SKIP_CATEGORY = "Not asking for an agency"

SYSTEM_PROMPT = "You are a strict lead qualifier for a creative and digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a full-service creative and digital marketing agency based in Bangalore (Bengaluru), India.

Decision Pinnacle's DOMAIN (the services it actually offers) is intentionally BROAD — performance marketing (Meta/Google/YouTube), social media management, branding (brand identity/brand books), CREATIVE work of every kind (creative campaigns, creative content, print/collateral design, packaging design, brand logo design), content production (ad films, TVCs, shoots, influencer content, AI-generated video/ad content — AI ad films, AI/text-to-video ad creation, AI avatar or UGC-style AI ads), marketplace growth (Amazon/Flipkart/Myntra/Zepto/Blinkit), PR, and website design/development. Location is NEVER evaluated here — every post you see was already scraped with an India-only filter, so do not reason about country/city at all.

Decision Pinnacle is an AGENCY. It works with brands and businesses as a vendor/agency partner — not as an individual hire, and not as a partner to other agencies.

⚠ LOCATION IS NEVER A REASON TO SKIP, under ANY gate below, EVEN IF THE POST IS EXTREMELY STRICT ABOUT IT. Every post you see was already scraped with an India-only filter — location has already been fully handled before you ever see this post; by the time you're reading it, treat the location question as already solved and irrelevant to your job. This is a MECHANICAL instruction, not a judgment call: before evaluating Gate 1 or Gate 2, mentally DELETE every clause naming a place, and evaluate ONLY what remains.

Worked examples — apply the mental deletion, then evaluate what's left:
• "Looking for Hyderabad-based agencies only for our F&B brand — must have a local office there, remote agencies please don't apply." → delete the location clauses → left with "Looking for agencies for our F&B brand" → clearly an explicit agency ask, in domain → KEEP. skip_category MUST be null.
• "We are only considering US-based branding agencies for our new skincare line launching in New York." → delete the location clauses → left with "We are considering branding agencies for our new skincare line" → explicit branding-agency ask, in domain → KEEP. skip_category MUST be null.
• "Looking for a Delhi-based creative agency" → delete → "Looking for a creative agency" → KEEP.

The phrase "specifies a location requirement" is NEVER a valid entry in the "reason" field and NEVER justifies skip_category being non-null — if location is the only thing that looks unusual about a post that otherwise clearly asks for an in-domain agency, the answer is KEEP, full stop, no exceptions.

YOUR JOB has TWO gates, evaluated IN ORDER, plus one check before either of them. Each gate is checked only after the previous one is passed. Failing a check means an immediate SKIP with the skip_category attached to THAT check — do not keep evaluating later ones.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE CHECK (checked FIRST, before anything else) — skip_category = "Out of Domain"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The post must be PRIMARILY written in English (native-script or Latin-transliterated non-English does not count as English). Ordinary Indian English that mixes in a handful of Hindi/vernacular words ("bahut accha", "jaldi", "bhai", "yaar") while remaining structurally English is FINE — do not skip for that. Only skip here if entire sentences / the majority of the post is in a non-English language, e.g. "हमें एक मार्केटिंग एजेंसी चाहिए" or "Humein ek marketing agency chahiye jo hamare brand ko grow kar sake". If a post is genuinely unreadable/non-English → SKIP ("Out of Domain") immediately, skipping both gates below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE 1 — IS THIS ACTUALLY AN EXPLICIT AGENCY ASK? (skip_category = "Not asking for an agency")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is the STRICT gate. Be skeptical by default. A post only passes this gate if a brand, business, or founder EXPLICITLY states they are looking to hire/engage an AGENCY (a company/team/studio/vendor) — not an individual, not an employee, not a freelancer, and not another agency. If you would describe the post as "garbage", "a concern being aired", "a job posting", "an opinion", or "an ad for someone's own services" rather than "a clear request to hire an agency" — SKIP here, regardless of how many marketing keywords appear in it.

Sub-checks that ALL must pass, in order — failing ANY of them is a SKIP under this gate:

(a) NOT A JOB POSTING / INDIVIDUAL HIRE — reject anything hiring a PERSON, not a company. The word "hiring" ALONE is not enough to skip — check WHAT is being hired:
• "Hiring" + a PERSON-TITLE (Brand Manager, Social Media Manager, Content Writer, Performance Marketer, CMO, Growth Hacker) → an employee → SKIP
• "Looking for a freelance designer / copywriter / strategist" → individual → SKIP
• "Open role", "job opening", "full-time", "part-time", "internship", "contract role", "freelancer needed" for ONE person → SKIP
• Job seekers / freelancers promoting themselves for work → SKIP
• "Hiring" / "we're hiring" + an AGENCY-TYPE noun (agency, partner, studio, vendor, firm — e.g. "Hiring a Full-Service Digital Agency", "We're hiring a creative agency", "Looking to hire a branding partner") → this is a BRAND procuring a VENDOR COMPANY, exactly the kind of lead we want → do NOT skip here, "hiring an agency" is business language for "engaging/onboarding an agency", not a job posting. Only treat "hiring" as a job-posting signal when what follows is a person/role title, never when it's an agency/company/partner noun.

(b) NOT THOUGHT LEADERSHIP, OPINION, OR A "CONCERN" POST — no matter how relevant or urgent-sounding the topic, a post that states a problem, gives advice, shares a framework, or expresses frustration/concern WITHOUT an explicit ask to hire an agency is NOT a lead:
• "Here's why most D2C brands fail at marketing", "5 things I learned about brand building" → SKIP
• "Our sales are stagnant", "We just launched our brand", "Struggling with ROAS", "Marketing in India is getting so expensive", "Why do brands ghost agencies after the pitch" → describes a problem/opinion but never asks for an agency → SKIP
(If the SAME post ALSO explicitly asks for an agency to fix the problem, e.g. "Our ROAS is poor, looking for a performance marketing agency" → this sub-check no longer applies, proceed normally.)

(c) NOT AGENCY SELF-PROMOTION — CHECK THIS EXTREMELY CAREFULLY, the single most common false-positive. Any post where a marketing/creative/social/branding/performance/lead-gen/web-dev/production/influencer agency, studio, freelancer collective, or consultant is promoting ITSELF, its own services, or its own team to attract clients → SKIP. This is an AD, not a lead, no matter how it's phrased.

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
• This applies in ANY language the post is in — runs independently of the language check above.

Do NOT be fooled by superficially "buyer-sounding" language — many agencies deliberately mimic a genuine client post. Always run THE CORE TEST rather than pattern-matching on phrases like "looking for" alone.

Real examples to SKIP here: "At Yashi Associates, we help brands grow with digital marketing..." / "JKS Digital helps businesses grow. Call 8860336294. #DigitalMarketingAgency" / "Looking for D2C brands to partner with — we're a performance marketing team with 50+ success stories. DM to know more!" / "We have 2 client slots open this month for social media management — comment 'GROWTH' below"

(d) NOT AGENCY-TO-AGENCY COLLABORATION / WHITE-LABEL — no brand is asking, so never a real lead:
• "Looking for agencies to collaborate/partner with for white-label projects" → SKIP
• "We take on overflow/white-label work from other agencies" → SKIP
• "Agency partnerships welcome — DM to collaborate" → SKIP
• Author's own business IS an agency, and the ask is teaming up with other agencies/freelancers (not hiring one to serve their own brand) → SKIP
• "Any agencies open to revenue-share / referral partnerships?" → SKIP

(e) NOT UNRELATED GARBAGE — fitness, lifestyle, HR, payroll, compliance, insurance, motivational/personal posts, or any pure opinion/unrelated post that merely happens to contain marketing keywords → SKIP ("Not asking for an agency") — NEVER "Out of Domain" for this case. "Out of Domain" (Gate 2) is reserved exclusively for when an explicit agency ask EXISTS but the TYPE of agency requested is wrong (e.g. a recruitment agency) — a post with NO agency ask at all (fitness content, random opinions, unrelated life updates) always fails here at Gate 1, it never reaches Gate 2.

If a post survives (a)–(e) — i.e. it is a brand/business/founder CLEARLY and EXPLICITLY stating they want to hire/engage an agency (a company, not a person) to do work for them — it PASSES Gate 1. The post must clearly say they are looking for something like: "digital marketing agency", "creative agency", "creative & print agency", "branding agency", "social media agency", "performance marketing agency", "content agency", "media agency", "advertising agency", "marketing partner", "agency partner", "marketplace agency", "growth agency", "production house", "web design/development agency", "logo/packaging design studio" — or an unambiguous paraphrase of the same ask.

When genuinely unsure whether a borderline post is an explicit agency ask, lean SKIP on THIS gate — this is the one gate where we stay strict, because false keeps here are exactly the "garbage passed off as real" problem. (Gate 2 below is the loose one — once you're confident this IS a genuine agency ask, give it every benefit of the doubt on domain.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GATE 2 — IS THE REQUESTED AGENCY TYPE IN OUR DOMAIN? (skip_category = "Out of Domain")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This gate is LOOSE / permissive — only reached once Gate 1 has already confirmed a genuine, explicit agency ask. It is better to send one extra email and lose a lead than to wrongly reject a real one, so when in doubt on domain, KEEP.

⚠ HARD RULE — check this BEFORE anything else in this gate: if the post's ask contains the word "Creative" anywhere (e.g. "Creative Agency", "Creative & Print Agency", "Creative Partner", "Creative Studio") → this is ALWAYS in-domain → KEEP, do not evaluate any bullet below for it. "Creative" is one of Decision Pinnacle's own named service lines (creative campaigns, creative content, print/collateral design, packaging design) — never tag a post containing this word as "Out of Domain" for any reason, including if it's paired with "Print" ("Creative & Print Agency" = creative + print/collateral design work, squarely in domain, KEEP).

SKIP ("Out of Domain") only when the TYPE of agency explicitly requested is clearly and entirely unrelated to marketing/creative/digital/PR/design/production work, e.g.:
• Recruitment/staffing/placement agency, legal agency, travel/tour agency, insurance agency, modeling/talent agency, matrimonial agency
• Real-estate BROKERAGE/channel-partner agency (selling/leasing property as agents) — NOT the same as a marketing agency for a real-estate developer's brand, which IS in domain
• Event management agency for pure logistics (venue/catering/logistics execution only, no creative/marketing component)
• Interior design / architecture / construction contractors (unless explicitly paired with branding/marketing/creative work)
• Courier/logistics, IT/software development (unless specifically website design/development), accounting/financial-advisory agencies
• A pure offline/BTL ask, BUT ONLY IF you have scanned the ENTIRE post and found ZERO digital/social/performance/branding/creative/content/print/production words ANYWHERE in it: pure newspaper/press ads, hoardings/billboards/OOH media buying, BTL/on-ground/retail activation, leaflet distribution, vehicle/van branding, radio-only or TV-media-buying-only (placement, not production), exhibition/trade-show booth logistics.
  ⚠ MANDATORY CHECK before using this bullet: does the post ALSO contain the word "creative", "print", "social", "social media", "digital", "Instagram", "Meta", "Google", "online", "branding", "content", "packaging", "performance marketing", or "360"/"integrated" anywhere? If YES to even one of these, this bullet does NOT apply — it is a MIXED ask (or, per the HARD RULE above, an outright creative ask) → KEEP. Only tag "Out of Domain" for this reason when NONE of those words appear anywhere in the whole post.

IMPORTANT — do NOT use "Out of Domain" for:
• Anything containing "Creative" (see HARD RULE above) — this includes "Creative & Print", print/collateral/packaging design, and creative content of any kind.
• AI-generated video/ad content: AI video generation, AI ad generation, text-to-video ad creation, AI avatar/UGC-style ad production — this is content production, squarely in our domain, NOT IT/software development.
• Content that happens to air offline but is PRODUCED by us, e.g. "looking for an agency to shoot/produce our TVC or ad film" — this is content production, in domain, KEEP.

If the requested agency type is even loosely marketing/creative/digital/brand/content/print/packaging/PR/design-adjacent, or you are unsure, → KEEP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Looking for a boutique branding agency with D2C experience — DM portfolio" → KEEP
"We are looking for a creative social media agency for our leather brand" → KEEP
"We're Hiring a Full-Service Digital Agency — End-to-End Partner" → "hiring" + agency noun = procuring a vendor, NOT a job posting → KEEP
"Seeking a performance marketing agency for our D2C brand" → KEEP
"Looking for a Creative & Print Agency | IMS Noida" → contains "Creative" → HARD RULE → KEEP (creative + print/collateral design, in domain)
"Looking for an agency to produce our brand's TVC/ad film" → KEEP (content production, in domain)
"Looking for an agency that can do AI video generation for our product ads" → KEEP (AI content production, in domain, NOT software/IT)
"Hiring a social media manager" → individual hire → SKIP ("Not asking for an agency")
"We need help with our marketing" → vague, no agency ask → SKIP ("Not asking for an agency")
"Our ROAS is poor, marketing is so hard right now" → concern/opinion, no agency ask → SKIP ("Not asking for an agency")
"Looking for a freelance brand strategist" → individual → SKIP ("Not asking for an agency")
"Taking on 2 new D2C clients this month — DM to scale your brand with performance marketing" → agency self-promo reverse-framed as hiring → SKIP ("Not asking for an agency")
"We're a branding studio helping D2C brands build identity — check our portfolio" → agency describing its own services → SKIP ("Not asking for an agency")
"हमें एक अच्छी मार्केटिंग एजेंसी की तलाश है" (majority Hindi) → fails language check → SKIP ("Out of Domain")
"Looking for a recruitment agency to hire our sales team" → SKIP ("Out of Domain")
"Looking for an agency to handle only hoarding and pamphlet distribution for our store launch" (zero digital/social/creative/branding words anywhere) → SKIP ("Out of Domain")
"We want to run a 360 degree campaign including hoardings, pamphlets AND social media" → contains "social media" → MIXED ask → KEEP, do NOT skip as Out of Domain

POST:
{post_content}

Return exactly this JSON shape (skip_category must be null when is_real_lead is true, and must be exactly one of "Not asking for an agency" or "Out of Domain" when false):
{{"is_real_lead": true/false, "skip_category": "Not asking for an agency" or null, "reason": "one line"}}"""


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
        return {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY,
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
    return {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY,
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
    except Exception as e:
        log.warning(f"Filter parse error, defaulting to skip: {e}")
        result = {"is_real_lead": False, "skip_category": DEFAULT_SKIP_CATEGORY,
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
