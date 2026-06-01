import asyncio
import json
from logger import get_logger
from config import has_openai, has_gemini, OPENAI_API_KEY, GEMINI_API_KEY

log = get_logger("gpt_filter")

SYSTEM_PROMPT = "You are a lead filter for a marketing consultancy. Return ONLY valid JSON. No markdown."

USER_TEMPLATE = """Read this LinkedIn post. Decide: KEEP (true) or SKIP (false)?

SKIP only if the post is clearly one of these exact cases:
1. A FREELANCER promoting their own services to get hired: "I offer X services", "hire me", "DM for freelance work", "available for projects"
2. A JOB SEEKER looking for employment: "looking for a job", "open to work", "seeking full-time role at an agency", "please refer me"
3. An AGENCY or company PROMOTING THEIR OWN work: "our agency helped brand X", "we delivered Y campaign", agency sharing their case studies or wins
4. Post is already CLOSED: "already found someone", "position filled", "no longer looking", "requirement closed", "update: hired"
5. Completely OFF-TOPIC: zero connection to business, marketing, or professional services

KEEP everything else. When in doubt → KEEP.

Do NOT reject a post for:
- Being vague or not mentioning a specific service
- Not being from India
- Not being a D2C brand
- Appearing to be thought leadership (still keep — they can still be reached)
- Not having "strong" or "explicit" intent
- Mentioning marketing without clearly hiring anyone

If there is any chance this person could benefit from a marketing agency → KEEP it.

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
    # Default KEEP on AI failure — filter is permissive, safer to include
    return {"is_real_lead": True, "reason": "AI unavailable — defaulting to keep"}


async def _filter_one_async(post: dict) -> tuple[dict, dict]:
    content = _get_content(post)
    try:
        result = await asyncio.to_thread(_filter_one, content)
        if not isinstance(result, dict) or "is_real_lead" not in result:
            raise ValueError("Malformed response")
    except Exception as e:
        log.warning(f"Filter parse error, defaulting to keep: {e}")
        result = {"is_real_lead": True, "reason": f"Parse error — defaulting to keep"}
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
