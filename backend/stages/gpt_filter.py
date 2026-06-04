import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY

log = get_logger("gpt_filter")

SYSTEM_PROMPT = "You are a lead qualifier for a digital marketing agency. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """You are qualifying LinkedIn posts for Decision Pinnacle — a digital marketing agency offering paid ads (Meta/Google), social media management, branding, creative campaigns, and marketplace (Amazon/Flipkart/Myntra/Zepto) growth services.

Your job: Decide whether this post represents a potential client — a business or founder who NEEDS or is OPEN TO hiring a digital marketing agency.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ KEEP (is_real_lead: true) if the post shows ANY of these signals:

STRONG signals (definitely keep):
• Explicitly asking for an agency or marketer: "looking for a digital marketing agency", "can anyone recommend a good agency"
• Seeking recommendations: "which agency should I hire?", "has anyone worked with a good social media agency?"
• Directly stating a marketing problem: "our ads aren't converting", "struggling with ROAS", "our social media has no engagement", "we tried ads but wasted money"
• Planning to outsource or scale marketing: "thinking of hiring an agency", "exploring options for marketing", "want to outsource our social media"
• Brand or product launch with a marketing need: "just launched our D2C brand", "launching on Amazon next month", "starting a new clothing line"

MODERATE signals (keep if the author is a business owner, founder, or brand — NOT a marketer/agency):
• A business owner sharing a growth challenge that marketing can solve: "struggling to get customers online", "need more brand visibility", "our online sales are stagnant"
• Job postings for marketing roles at a company (Head of Marketing, Digital Marketing Manager, Social Media Manager) — signals the company is investing in marketing and could need agency support
• A founder asking for advice on scaling, growth, or customer acquisition
• Company announcing a new product/service or expansion (they will need marketing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ SKIP (is_real_lead: false) — these are NOT leads:

• Thought leadership / opinion posts: marketers, consultants, or agency owners sharing tips, frameworks, or opinions about digital marketing — e.g. "Here are 5 reasons most brands fail at marketing", "Most businesses don't have a budget problem, they have a structure problem", "Why your marketing strategy isn't working"
• Agency self-promotion: "our agency delivered X results", "we helped brand Y grow", "check out our case study", "we increased ROAS by 3x"
• Freelancers promoting their own services: "I offer X services", "hire me", "available for projects", "DM for freelance work"
• Job seekers looking for employment: "open to work", "seeking a role", "looking for a job in digital marketing"
• Posts already closed or filled: "already hired", "position filled", "found an agency"
• Fitness, wellness, sports, running, lifestyle posts — even if the person has a company title
• HR, payroll, compliance, recruitment, insurance, legal posts with no marketing angle
• Pure news, statistics, industry reports, or platform updates (e.g. "Meta changed its algorithm")
• Motivational quotes, personal achievements, or life updates with no business/marketing need
• Marketing coaches or consultants teaching others — they ARE the service, not the buyer
• Posts where "marketing" or "agency" is just mentioned in passing with no personal buying intent

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY RULE: Ask yourself — "Is this person/company a potential buyer of marketing services?"
A marketer writing ABOUT marketing ≠ a buyer. A business owner who NEEDS marketing = a buyer.

"Most businesses have a marketing structure problem" → opinion by a marketer → SKIP
"We're launching our clothing brand and need marketing help" → real need → KEEP
"Hiring a Digital Marketing Manager at our startup" → company investing in marketing → KEEP
"I'm a digital marketing freelancer, hire me" → service provider → SKIP

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
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(post_content=post_content)
    resp = model.generate_content(prompt)
    return json.loads(_strip_json(resp.text))


def _call_openai(post_content: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
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
    last_err = None
    if has_openai():
        try:
            return _call_openai(post_content)
        except Exception as e:
            last_err = e
            log.warning(f"OpenAI filter failed, trying Gemini: {e}")
    if has_gemini():
        try:
            return _call_gemini(post_content)
        except Exception as e:
            last_err = e
            log.warning(f"Gemini filter failed: {e}")
    log.error(f"Both AI providers failed: {last_err}")
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

    batch_size = 5
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
