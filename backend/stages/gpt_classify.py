import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_classify")

_openai_client = None
_gemini_model = None

USER_TEMPLATE = """You are analyzing a LinkedIn post for Decision Pinnacle — a full-service creative and digital marketing agency in India.

Decision Pinnacle classifies every qualified lead into exactly ONE of 11 SERVICE CATEGORIES based on WHAT SERVICE the lead is asking for — not the brand's industry — EXCEPT for "Creative", which additionally tries to identify the brand's industry vertical (see below).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SERVICE CATEGORIES

1. "Growth" — performance marketing (Meta/Google/YouTube ads), marketplace and quick-commerce growth (Amazon, Flipkart, Myntra, Zepto, Blinkit), ROAS/funnel/conversion-focused asks, D2C scaling.
   Signals: "performance marketing", "ROAS", "paid ads", "Meta ads", "Google ads", "marketplace growth", "Amazon/Flipkart/Myntra/Zepto/Blinkit", "scale our D2C brand", "growth agency", "growth marketing".

2. "Production" — making the physical/video creative asset itself: ad films, TVCs, photo shoots, video shoots, post-production, AND AI-generated video/ad content (AI video generation, AI ad generation, text-to-video ad creation, AI avatar/UGC-style ad production) — these are content production too, not IT/software or out of domain.
   Signals: "production house", "video production agency", "ad film", "TVC", "shoot", "photoshoot", "video production", "campaign film", "AI video generation", "AI ad generation", "AI-generated ads", "text-to-video", "AI avatar ads", "UGC-style AI ads".

3. "Influencer Marketing" — influencer/creator partnerships, UGC, influencer campaigns.
   Signals: "influencer marketing agency", "influencer campaign", "creator partnership", "UGC content", "influencer collaboration", "creator-led campaign".

4. "Branding" — brand identity, brand book, naming, positioning, logo design, packaging design.
   Signals: "branding agency", "brand identity", "brand book", "logo design", "packaging design", "rebrand", "brand strategy", "brand positioning".

5. "Creative" — campaign concept/creative direction and content strategy asks broader than production/influencer/branding alone (e.g. general "creative agency", "creative partner", "social media agency", "content strategy", "campaign idea").
   Signals: "creative agency", "creative partner", "social media agency", "content strategy", "campaign concept", "content calendar".
   IMPORTANT: If (and only if) the category is "Creative", you must ALSO determine the brand's INDUSTRY VERTICAL from this list, using these definitions:
   - "FMCG" — packaged food/snacks, beverages, dairy, edible oils, home care, plain hygiene staples, grocery/CPG, supplements, pet food.
   - "Real Estate" — property developers/builders, brokers, construction, project-launch marketing.
   - "Apparel" — clothing/fashion for ADULTS, footwear, fashion accessories, textiles. (Use Kids instead if explicitly for children/babies.)
   - "Kids" — baby/children's products of ANY type — ALWAYS outranks Apparel or Beauty when the product is explicitly for infants/children.
   - "Beauty" — cosmetics, skincare, haircare, makeup, fragrance, grooming (adult, non-baby).
   If the industry fits one of these 5 → output category as "Creative - <Vertical>" exactly, e.g. "Creative - FMCG", "Creative - Real Estate", "Creative - Apparel", "Creative - Kids", "Creative - Beauty".
   If the industry does NOT fit any of these 5 (e.g. SaaS, fintech, healthcare, education, automotive, B2B services), or genuinely cannot be determined → output bare "Creative" instead (the main/parent category — NOT "Generic"). This keeps the lead correctly flagged as a creative-type ask even without an industry-specific angle.

6. "Generic" — use this ONLY when the post doesn't clearly fit Growth, Production, Influencer Marketing, Branding, OR Creative at all — i.e. the service type itself genuinely cannot be determined from the post or author context. Never guess wildly. Generic is now the last resort, not a catch-all for Creative leads with an unclear industry — those go to bare "Creative" (see above).

TIEBREAKERS (apply in this order — never skip these):
- A request specifically for a "production house" / "video production agency" is "Production" even if it's for a creative campaign — production is the literal deliverable being asked for.
- A request for a general "social media agency" or "creative agency" (no specific production/influencer/branding emphasis) is "Creative", not "Branding".
- A request explicitly emphasizing brand identity/logo/brand book/naming is "Branding", even if it also mentions general creative work.
- If a post asks for MULTIPLE services with no clear primary, prefer in this order: Branding > Production > Influencer Marketing > Growth > Creative (the more specific/concrete ask wins over the broader "Creative" catch-all).
- Within "Creative" only: baby/kids product → ALWAYS "Creative - Kids", even if also apparel or FMCG. Cosmetic/skincare/makeup → "Creative - Beauty" even if sold via FMCG-style D2C channels. Plain hygiene/cleaning staple with no beauty positioning → "Creative - FMCG". Industry doesn't fit any of the 5, or can't be determined → bare "Creative".
- Cannot tell the service type AT ALL (not even Creative) → "Generic". Never guess wildly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extract FOUR things from the post below:

1. EMAIL: Scan the entire post for any email address.
   - Look for direct emails: name@company.com
   - Look for obfuscated emails: "name [at] company [dot] com", "name(at)company.com", "reach me at name@..." — convert to standard format
   - If found, return the email string. If not found, return null.

2. COMPANY NAME: Identify the brand/company the author represents (NOT Decision Pinnacle, and not a recruiter's own staffing agency unless that agency is itself the client looking to hire).
   - Prefer an explicit company/brand name mentioned in the post content (e.g. "We at Sleepyhead are looking for..." → "Sleepyhead").
   - If not in the post, infer it from the AUTHOR HEADLINE (e.g. "Founder at Sleepyhead" → "Sleepyhead", "Marketing Lead, XYZ Pvt Ltd" → "XYZ Pvt Ltd").
   - If genuinely no company name is identifiable from either source, return null. Do not invent a name.

3. CATEGORY: Pick exactly ONE of: "Growth", "Production", "Influencer Marketing", "Branding", "Creative", "Creative - FMCG", "Creative - Real Estate", "Creative - Apparel", "Creative - Kids", "Creative - Beauty", "Generic" using the definitions and tiebreakers above.

4. CONTACT METHOD: How does the post tell people to reach out? Pick exactly ONE of only two values:
   - "Email" — an email address is given anywhere in the post (e.g. "email me at x@y.com", "send your portfolio to x@y.com").
   - "Phone/LinkedIn/Not Specified" — everything else: a phone/WhatsApp number is given instead, OR the post says to message/DM/comment ("DM me", "comment below", "ping me"), OR no contact method is mentioned at all. All three of these cases share this one combined value — do not distinguish between them.

POST CONTENT:
{post_content}

AUTHOR NAME: {author_name}
AUTHOR HEADLINE: {author_headline}

Return ONLY this exact JSON (no markdown, no explanation):
{{"email_in_post": "email@example.com or null", "company_name": "Company Name or null", "category": "Growth", "contact_method": "Email"}}"""

VALID_CATEGORIES = {
    "Growth", "Production", "Influencer Marketing", "Branding", "Creative",
    "Creative - FMCG", "Creative - Real Estate", "Creative - Apparel",
    "Creative - Kids", "Creative - Beauty", "Generic",
}
VALID_CONTACT_METHODS = {"Email", "Phone/LinkedIn/Not Specified"}
DEFAULT_CONTACT_METHOD = "Phone/LinkedIn/Not Specified"


def _truncate(text: str, max_chars: int = 3000) -> str:
    return text[:max_chars] if len(text) > max_chars else text


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _call_openai(post_content: str, author_name: str, author_headline: str) -> dict:
    from openai import OpenAI
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = USER_TEMPLATE.format(
        post_content=_truncate(post_content),
        author_name=author_name,
        author_headline=author_headline,
    )
    resp = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=150,
    )
    return json.loads(_strip_json_fences(resp.choices[0].message.content))


def _call_gemini(post_content: str, author_name: str, author_headline: str) -> dict:
    import google.generativeai as genai
    global _gemini_model
    if _gemini_model is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = USER_TEMPLATE.format(
        post_content=_truncate(post_content),
        author_name=author_name,
        author_headline=author_headline,
    )
    resp = _gemini_model.generate_content(prompt)
    return json.loads(_strip_json_fences(resp.text))


def _classify_one(post: dict) -> dict:
    from post_fields import get_content, get_author_name, get_author_headline
    content = get_content(post)
    name = get_author_name(post)
    headline = get_author_headline(post)
    providers = []
    if has_gemini():
        providers.append(("gemini", lambda: _call_gemini(content, name, headline)))
    if has_openai():
        providers.append(("openai", lambda: _call_openai(content, name, headline)))

    if not providers:
        log.error("No AI providers configured for classify stage")
        return {"email_in_post": None, "company_name": None, "category": "Generic", "contact_method": DEFAULT_CONTACT_METHOD}

    ordered_names = provider_order([provider_name for provider_name, _ in providers])
    provider_map = {provider_name: func for provider_name, func in providers}
    last_err = None
    failed = []

    for idx, provider_name in enumerate(ordered_names):
        try:
            return call_with_retries(provider_name, provider_map[provider_name], log, "classify")
        except Exception as e:
            last_err = e
            failed.append(provider_display_name(provider_name))
            if idx + 1 < len(ordered_names):
                next_provider = provider_display_name(ordered_names[idx + 1])
                log.warning(
                    f"{provider_display_name(provider_name)} classify failed after retries, "
                    f"trying {next_provider}: {e}"
                )

    log.error(
        f"All configured AI providers failed in classify ({', '.join(failed)}): {last_err}"
    )
    return {"email_in_post": None, "company_name": None, "category": "Generic", "contact_method": DEFAULT_CONTACT_METHOD}


async def _classify_one_async(post: dict) -> tuple[dict, dict]:
    try:
        result = await asyncio.to_thread(_classify_one, post)
        if not isinstance(result, dict):
            raise ValueError("Non-dict response")
        if result.get("category") not in VALID_CATEGORIES:
            log.warning(f"Invalid category '{result.get('category')}' — falling back to Generic")
            result["category"] = "Generic"
        email = result.get("email_in_post")
        if email and (str(email).lower() in ("null", "none", "") or "@" not in str(email)):
            result["email_in_post"] = None
        company = result.get("company_name")
        if company and str(company).strip().lower() in ("null", "none", ""):
            result["company_name"] = None
        # If we found a real email, contact method should always say "Email" regardless
        # of what the model picked — the email itself is the most reliable signal.
        # Conversely, "Email" is NEVER valid without an actual email_in_post value —
        # observed in testing that the model sometimes returns contact_method="Email"
        # even when email_in_post is null (an internal inconsistency in its own raw
        # output, not something a value-membership check alone catches, since "Email"
        # is itself a recognized value). Force the fallback in that case.
        if result.get("email_in_post"):
            result["contact_method"] = "Email"
        elif result.get("contact_method") not in VALID_CONTACT_METHODS or result.get("contact_method") == "Email":
            result["contact_method"] = DEFAULT_CONTACT_METHOD
    except Exception as e:
        log.warning(f"Classify parse error: {e}")
        result = {"email_in_post": None, "company_name": None, "category": "Generic", "contact_method": DEFAULT_CONTACT_METHOD}
    return post, result


async def run_gpt_classify(real_posts: list[dict], emit) -> list[dict]:
    await emit({"event": "stage_start", "stage": 4, "name": "AI Classify",
                "message": "Extracting emails and classifying leads into service categories..."})

    total = len(real_posts)
    enriched = []
    batch_size = AI_BATCH_SIZE

    for i in range(0, total, batch_size):
        batch = real_posts[i:i + batch_size]
        tasks = [_classify_one_async(p) for p in batch]
        results = await asyncio.gather(*tasks)

        for post, classification in results:
            post["_email_in_post"] = classification.get("email_in_post")
            post["_company_name"] = classification.get("company_name")
            post["_category"] = classification.get("category", "Generic")
            post["_contact_method"] = classification.get("contact_method", DEFAULT_CONTACT_METHOD)
            enriched.append(post)

        processed = min(i + batch_size, total)
        await emit({
            "event": "progress",
            "stage": 4,
            "message": f"Classified {processed}/{total} leads",
            "processed": processed,
        })

    category_counts = {}
    for p in enriched:
        cat = p.get("_category", "Generic")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    summary = " | ".join(f"{k}: {v}" for k, v in sorted(category_counts.items()))

    await emit({
        "event": "stage_complete",
        "stage": 4,
        "name": "AI Classify",
        "metric": f"{total} classified — {summary}",
        "processed": total,
    })
    log.info(f"STAGE 4 | Classified {total} leads: {summary}")
    return enriched
