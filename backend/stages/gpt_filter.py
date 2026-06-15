import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY
from ai_utils import AI_BATCH_SIZE, call_with_retries, provider_display_name, provider_order

log = get_logger("gpt_filter")

_openai_client = None
_gemini_model = None

SYSTEM_PROMPT = "You are a strict lead qualifier for a creative and digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a full-service creative and digital marketing agency based in India. Services: performance marketing (Meta/Google), social media management, branding, creative campaigns, content production, marketplace growth (Amazon/Flipkart/Myntra/Zepto), and PR.

Decision Pinnacle is an AGENCY. It works with brands and businesses as a vendor/agency partner — not as an individual hire.

YOUR ONLY JOB: Identify posts where a brand, business, or founder is EXPLICITLY stating they are looking to hire or engage an AGENCY (not an individual, not an employee, not a freelancer — an agency).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ KEEP (is_real_lead: true) ONLY if the post EXPLICITLY asks for an AGENCY

The post must clearly say they are looking for one of these:
→ "digital marketing agency", "creative agency", "branding agency", "social media agency", "performance marketing agency", "content agency", "media agency", "advertising agency", "marketing partner", "agency partner", "marketplace agency", "growth agency", "production house"

Examples that MUST be kept:
• "Looking for a boutique branding agency with D2C experience — DM portfolio"
• "We are looking for a creative social media agency for our leather brand"
• "Can anyone recommend a good digital marketing agency in India?"
• "Seeking a performance marketing agency for our D2C brand"
• "We want to onboard a creative agency for our upcoming product launch"
• "Looking for an agency to handle our Amazon and Flipkart marketplace"
• "Any good branding or creative agency for a fashion label? Comment below"
• "We need a social media agency, preferably with experience in beauty/FMCG"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ SKIP (is_real_lead: false) — everything else, including:

JOB POSTINGS (skip all individual/employee hires):
• Hiring a Brand Manager, Marketing Manager, Social Media Manager, Content Writer, Performance Marketer, CMO, Growth Hacker — these are EMPLOYEE hires, not agency hires → SKIP
• "Looking for a freelance designer / copywriter / strategist" → individual hire → SKIP
• "Open role: Digital Marketing Executive" → SKIP
• ANY post with "hiring", "job opening", "full-time", "part-time", "internship", "contract role", "freelancer needed" for an individual person → SKIP

THOUGHT LEADERSHIP & OPINIONS (no matter how relevant the topic):
• Posts sharing tips, frameworks, opinions, or commentary about marketing, branding, or D2C → SKIP
• "Here's why most D2C brands fail at marketing" → SKIP
• "The state of digital advertising in 2025" → SKIP
• "5 things I learned about brand building" → SKIP
• Industry news, trend analysis, platform updates → SKIP

COMPETITOR AGENCY SELF-PROMOTION (very common — skip all of these):
Any post where a digital marketing / creative / social media / branding / performance marketing / lead generation / web development agency is promoting ITSELF to find clients → SKIP immediately.

Patterns to detect:
• "At [Agency Name], we help businesses with X, Y, Z" — agency introducing itself → SKIP
• Post lists services like ✅ Performance Marketing ✅ Social Media ✅ Branding ✅ Lead Generation → agency ad → SKIP
• "Looking for a digital marketing agency? Contact us / We are here / Call us" — agency trying to get clients by pretending to be a solution → SKIP
• Hashtags like #DigitalMarketingAgency #SocialMediaAgency #BrandingAgency #LeadGenerationAgency #MarketingAgencyDelhi — clear agency self-promo → SKIP
• "We build growth systems / We run ads / We create campaigns for your business" — agency pitch → SKIP
• The author themselves IS the agency offering the service — they are pitching, not buying → SKIP
• Posts in any language (Malayalam, Hindi, Tamil, English, etc.) where an agency is marketing its own services → SKIP

NOTE: A phone number or website alone does NOT make a post a skip. Only skip if the overall post is clearly an agency advertising its own services to find clients.

Real examples to SKIP:
→ "At Yashi Associates, we help brands grow with digital marketing, social media management..." → agency ad → SKIP
→ "JKS Digital helps businesses grow. Call 8860336294. #DigitalMarketingAgency" → agency ad → SKIP
→ "Brixads helps businesses across Kerala with branding and campaigns. Call 9744400414" → agency ad → SKIP

VAGUE MARKETING CHALLENGES (without explicitly asking for an agency):
• "Our sales are stagnant" — no mention of needing an agency → SKIP
• "We just launched our brand" — no mention of needing an agency → SKIP
• "Struggling with ROAS" — no mention of needing an agency → SKIP
• Any post describing a business problem WITHOUT explicitly asking for an agency → SKIP

OTHER SKIPS:
• Job seekers, freelancers promoting themselves → SKIP
• Fitness, lifestyle, HR, payroll, compliance, insurance posts → SKIP
• Motivational or personal posts → SKIP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE SINGLE TEST: Does this post EXPLICITLY say they want to hire or work with an AGENCY?
If yes → KEEP. If no, or if it could mean an individual hire → SKIP.

"Looking for a social media agency for our apparel brand" → explicitly wants agency → KEEP
"Hiring a social media manager" → individual hire, not agency → SKIP
"We need help with our marketing" → vague, no agency mentioned → SKIP
"Recommend a branding agency" → explicitly wants agency → KEEP
"Looking for a freelance brand strategist" → individual, not agency → SKIP
"Our ROAS is poor" → no agency ask → SKIP

When in doubt → SKIP.

POST:
{post_content}

Return exactly: {{"is_real_lead": true/false, "reason": "one line"}}"""


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
        max_tokens=100,
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
        return {"is_real_lead": False, "reason": "AI unavailable — defaulting to skip"}

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
    return {"is_real_lead": False, "reason": "AI unavailable — defaulting to skip"}


async def _filter_one_async(post: dict) -> tuple[dict, dict]:
    content = _get_content(post)
    try:
        result = await asyncio.to_thread(_filter_one, content)
        if not isinstance(result, dict) or "is_real_lead" not in result:
            raise ValueError("Malformed response")
    except Exception as e:
        log.warning(f"Filter parse error, defaulting to skip: {e}")
        result = {"is_real_lead": False, "reason": f"Parse error — defaulting to skip"}
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
            if verdict.get("is_real_lead"):
                post["_filter_reason"] = verdict.get("reason", "")
                post["_lead_status"] = "REAL"
                real_posts.append(post)
            else:
                post["_filter_reason"] = verdict.get("reason", "")
                post["_lead_status"] = f"SKIPPED ({verdict.get('reason', '')})"
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
