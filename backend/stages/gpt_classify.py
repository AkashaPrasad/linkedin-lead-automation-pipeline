import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_classify")

_openai_client = None
_gemini_model = None

USER_TEMPLATE = """You are analyzing a LinkedIn post for Decision Pinnacle — a full-service creative and digital marketing agency in India that works across multiple consumer industries.

Decision Pinnacle classifies every qualified lead into exactly ONE of 6 INDUSTRY VERTICALS based on the AUTHOR'S BRAND/BUSINESS — never based on what marketing service they're asking for.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INDUSTRY VERTICALS

1. "FMCG" — Fast-Moving Consumer Goods: packaged food & snacks, beverages, dairy, edible oils, home care / cleaning products, plain hygiene staples (soap, toothpaste, detergent, sanitizer), grocery/CPG, nutrition & wellness supplements, pet food, and other fast-turnover consumable goods.
   Signals: "FMCG", "CPG", "packaged food", "snacks brand", "beverage", "D2C food brand", "home care", "consumer goods", "grocery".

2. "Real Estate" — property developers/builders, real estate brokers and consultants, construction companies, property portals, project-launch marketing (apartments/villas/plots/commercial spaces), real estate finance/home-loan marketing.
   Signals: "real estate", "property", "builder", "developer", "apartments", "villas", "plots", "RERA", "construction", "realty".

3. "Apparel" — clothing and fashion brands for ADULTS, footwear, fashion accessories, textiles, ethnic/western wear, activewear. (Use "Kids" instead if the apparel is specifically for children/babies.)
   Signals: "apparel", "fashion brand", "clothing", "footwear", "ethnic wear", "D2C fashion".

4. "Kids" — baby and children's products of ANY type: baby care, diapers, baby gear (strollers/cribs), kids' clothing/footwear/toys, maternity products, parenting brands. Kids/baby ALWAYS outranks Apparel or Beauty when the product is explicitly for infants/children.
   Signals: "baby", "kids", "infant", "toddler", "parenting", "maternity", "toys", "diaper", "baby care", "children's".

5. "Beauty" — cosmetics, skincare, haircare, makeup, fragrance/perfume, grooming, and beauty & personal care (BPC) brands for adults (non-baby).
   Signals: "beauty", "skincare", "cosmetics", "makeup", "haircare", "BPC", "grooming", "fragrance", "perfume", "personal care" (only when clearly cosmetic, not a plain hygiene staple).

6. "Generic" — anything that does not clearly fit one of the 5 verticals above (e.g. SaaS/tech, fintech, healthcare, education, automotive, B2B services, home decor/furniture), OR the post equally spans multiple unrelated verticals, OR the industry genuinely cannot be determined from the post or author context.

TIEBREAKERS (apply in this order — never skip these):
- Baby/kids product → ALWAYS "Kids", even if it's also apparel ("baby clothing"), beauty ("baby skincare"), or FMCG ("baby food").
- Cosmetic/skincare/makeup product → "Beauty", even if sold through FMCG-style D2C channels.
- Plain hygiene/cleaning staple (soap, toothpaste, detergent, sanitizer) with NO beauty/cosmetic positioning → "FMCG".
- Food, beverage, or home-care product → "FMCG".
- Real estate company that also mentions interior design/home decor as a side line → still "Real Estate" if the core business is property sales/development; if the post is ONLY about home decor/furniture with no property angle → "Generic".
- Two unrelated industries mentioned with equal weight, neither dominant → "Generic".
- Cannot tell the industry from the post or author headline/company → "Generic". Never guess wildly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extract THREE things from the post below:

1. EMAIL: Scan the entire post for any email address.
   - Look for direct emails: name@company.com
   - Look for obfuscated emails: "name [at] company [dot] com", "name(at)company.com", "reach me at name@..." — convert to standard format
   - If found, return the email string. If not found, return null.

2. COMPANY NAME: Identify the brand/company the author represents (NOT Decision Pinnacle, and not a recruiter's own staffing agency unless that agency is itself the client looking to hire).
   - Prefer an explicit company/brand name mentioned in the post content (e.g. "We at Sleepyhead are looking for..." → "Sleepyhead").
   - If not in the post, infer it from the AUTHOR HEADLINE (e.g. "Founder at Sleepyhead" → "Sleepyhead", "Marketing Lead, XYZ Pvt Ltd" → "XYZ Pvt Ltd").
   - If genuinely no company name is identifiable from either source, return null. Do not invent a name.

3. CATEGORY: Pick exactly ONE of: "FMCG", "Real Estate", "Apparel", "Kids", "Beauty", "Generic" using the vertical definitions and tiebreakers above.

POST CONTENT:
{post_content}

AUTHOR NAME: {author_name}
AUTHOR HEADLINE: {author_headline}

Return ONLY this exact JSON (no markdown, no explanation):
{{"email_in_post": "email@example.com or null", "company_name": "Company Name or null", "category": "FMCG"}}"""

VALID_CATEGORIES = {"FMCG", "Real Estate", "Apparel", "Kids", "Beauty", "Generic"}


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
        return {"email_in_post": None, "company_name": None, "category": "Generic"}

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
    return {"email_in_post": None, "company_name": None, "category": "Generic"}


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
    except Exception as e:
        log.warning(f"Classify parse error: {e}")
        result = {"email_in_post": None, "company_name": None, "category": "Generic"}
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
