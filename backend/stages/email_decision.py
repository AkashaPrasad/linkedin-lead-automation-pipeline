import asyncio
from datetime import datetime
from logger import get_logger

log = get_logger("email_decision")


async def run_email_decision(posts: list[dict], emit) -> list[dict]:
    await emit({"event": "stage_start", "stage": 7, "name": "Email Decision", "message": "Selecting best email for each lead..."})

    with_email = 0
    no_email = 0

    for post in posts:
        email_from_post = post.get("_email_in_post")
        apollo_email = post.get("_apollo_email")

        if email_from_post:
            post["_final_email"] = email_from_post
            post["_has_email"] = "YES"
            with_email += 1
        elif apollo_email:
            post["_final_email"] = apollo_email
            post["_has_email"] = "YES"
            with_email += 1
        else:
            post["_final_email"] = None
            post["_has_email"] = "NO"
            post["_sent_status"] = "NO_EMAIL"
            # Stamp a resolution timestamp here too, not just on SENT — every
            # REAL lead should end up with a definitive terminal status
            # (sent or no_email) and a record of when that was decided,
            # rather than only successful sends being timestamped.
            post["_sent_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            no_email += 1

    await emit({
        "event": "stage_complete",
        "stage": 7,
        "name": "Email Decision",
        "metric": f"{with_email} with email, {no_email} without",
        "with_email": with_email,
        "no_email": no_email,
    })
    log.info(f"STAGE 7 | Email decision: {with_email} have email, {no_email} do not")
    return posts
