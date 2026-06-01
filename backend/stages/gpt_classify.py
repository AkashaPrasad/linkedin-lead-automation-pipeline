import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY

log = get_logger("gpt_classify")

USER_TEMPLATE = """You are analyzing a LinkedIn post for Decision Pinnacle — a D2C growth and marketing consultancy in India.

Decision Pinnacle's service lines:
• Growth: Meta/Google/YouTube paid performance, ROAS optimisation, CAC reduction, D2C brand scaling, conversion rate, retargeting, funnel strategy
• Branding: brand identity, brand book, brand positioning, visual identity, rebranding, brand persona, brand strategy
• Creative & Campaign: ad films, TVCs, brand films, shoots (catalogue/lifestyle), UGC, influencer campaigns, video production, campaign concepts
• Social Media: Instagram/LinkedIn organic management, reels, content calendar, community management, social media strategy
• Marketplace: Amazon / Myntra / Flipkart / Zepto / Blinkit / Meesho / FirstCry — campaign management, TACOS, ROAS on marketplace, PDP SEO, keyword strategy, BSR improvement, new channel launch, quick commerce, DSP, listing optimisation, pricing strategy on marketplace, inventory management
• Generic: general marketing agency need, unclear mix, or equally mentions multiple services

Extract two things from the post below:

1. EMAIL: Scan the entire post for any email address.
   - Look for direct emails: name@company.com
   - Look for obfuscated emails: "name [at] company [dot] com", "name(at)company.com", "reach me at name@..." — convert to standard format
   - If found, return the email string. If not found, return null.

2. CATEGORY: Based on the author's industry context AND what service they appear to need, pick exactly ONE:
   - "Growth" — they need paid performance marketing, ROAS improvement, D2C revenue scaling via ads
   - "Branding" — they need brand identity, positioning, brand strategy, visual identity
   - "Creative & Campaign" — they need ad films, shoots, production, influencer campaigns, campaign concepts
   - "Social Media" — they need organic social media management, Instagram/LinkedIn content, reels strategy
   - "Marketplace" — they need help with Amazon/Myntra/Flipkart/Zepto/Blinkit/quick commerce sales and management
   - "Generic" — unclear need, multiple services equally, or general "marketing agency" requirement

   Tiebreaker rules:
   - If post mentions both ads AND marketplace, pick "Marketplace" if they specifically mention Amazon/Myntra/Zepto channels; otherwise "Growth"
   - Real estate companies → usually "Social Media" or "Creative & Campaign" (they rarely run D2C performance marketing)
   - D2C brands mentioning revenue/ROAS/CAC → "Growth"
   - D2C brands mentioning "we just launched on Amazon" or "struggling with Myntra" → "Marketplace"
   - When genuinely unclear → "Generic"

POST CONTENT:
{post_content}

AUTHOR NAME: {author_name}
AUTHOR HEADLINE: {author_headline}

Return ONLY this exact JSON (no markdown, no explanation):
{{"email_in_post": "email@example.com or null", "category": "Growth"}}"""

VALID_CATEGORIES = {"Growth", "Branding", "Creative & Campaign", "Social Media", "Marketplace", "Generic"}


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
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = USER_TEMPLATE.format(
        post_content=_truncate(post_content),
        author_name=author_name,
        author_headline=author_headline,
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=150,
    )
    return json.loads(_strip_json_fences(resp.choices[0].message.content))


def _call_gemini(post_content: str, author_name: str, author_headline: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = USER_TEMPLATE.format(
        post_content=_truncate(post_content),
        author_name=author_name,
        author_headline=author_headline,
    )
    resp = model.generate_content(prompt)
    return json.loads(_strip_json_fences(resp.text))


def _classify_one(post: dict) -> dict:
    from post_fields import get_content, get_author_name, get_author_headline
    content = get_content(post)
    name = get_author_name(post)
    headline = get_author_headline(post)
    last_err = None

    if has_openai():
        try:
            return _call_openai(content, name, headline)
        except Exception as e:
            last_err = e
            log.warning(f"OpenAI classify failed, trying Gemini: {e}")
    if has_gemini():
        try:
            return _call_gemini(content, name, headline)
        except Exception as e:
            last_err = e
            log.warning(f"Gemini classify failed: {e}")
    log.error(f"Both AI providers failed in classify: {last_err}")
    return {"email_in_post": None, "category": "Generic"}


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
    except Exception as e:
        log.warning(f"Classify parse error: {e}")
        result = {"email_in_post": None, "category": "Generic"}
    return post, result


async def run_gpt_classify(real_posts: list[dict], emit) -> list[dict]:
    await emit({"event": "stage_start", "stage": 4, "name": "AI Classify",
                "message": "Extracting emails and classifying leads into service categories..."})

    total = len(real_posts)
    enriched = []
    batch_size = 5

    for i in range(0, total, batch_size):
        batch = real_posts[i:i + batch_size]
        tasks = [_classify_one_async(p) for p in batch]
        results = await asyncio.gather(*tasks)

        for post, classification in results:
            post["_email_in_post"] = classification.get("email_in_post")
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
