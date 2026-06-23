import asyncio
import time
from datetime import datetime
from logger import get_logger
from stages.alerts import send_alert
from stages.apify_scraper import run_apify
from stages.deduplication import run_deduplication
from stages.gpt_filter import run_gpt_filter
from stages.gpt_classify import run_gpt_classify
from stages.sheets_writer import open_sheets, run_sheets_writer, finalize_sheet_columns
from stages.apollo_enricher import run_apollo_enricher
from stages.email_decision import run_email_decision
from stages.brevo_sender import run_brevo_sender
import checkpoint as cp

log = get_logger("pipeline")

STAGE_NAMES = {
    1: "Apify Scraper",
    2: "Deduplication",
    3: "AI Filter",
    4: "AI Classify",
    5: "Google Sheets",
    6: "Apollo Enrichment",
    7: "Email Decision",
    8: "Email Sender",
    9: "Finalize Sheets",
}


async def _run_stages_6_to_9(
    emit,
    real_posts: list[dict],
    master_ws,
    daily_ws,
    master_start_row: int | None,
    daily_start_row: int,
    cfg: dict,
    dry_run: bool,
    stats: dict,
    pipeline_start: float,
    skipped_posts_count: int = 0,
) -> None:
    """Runs Stages 6–9. Used by both fresh run and resume."""
    sending = cfg.get("sending", {})
    enrichment = cfg.get("enrichment", {})

    # ── Stage 6: Apollo Enrichment ─────────────────────────────────────
    apollo_enabled = enrichment.get("apollo_enabled", True)
    max_enrich = enrichment.get("max_enrichment_per_run", 100)

    if apollo_enabled:
        real_posts = await run_apollo_enricher(real_posts, master_ws, daily_ws, emit, max_enrichment=max_enrich)
    else:
        await emit({"event": "stage_start", "stage": 6, "name": "Apollo Enrichment",
                    "message": "Apollo enrichment disabled"})
        await emit({"event": "stage_complete", "stage": 6, "name": "Apollo Enrichment",
                    "metric": "Skipped (disabled)", "enriched": 0, "not_found": 0})

    enriched = sum(1 for p in real_posts if p.get("_apollo_email"))
    stats["enriched"] = enriched
    await emit({"event": "stats", **stats})
    await send_alert(f"✅ Stage 6 done — {enriched} emails enriched via Apollo")

    # Save checkpoint after Stage 6 (in case Stage 7/8 fails)
    cp.save(6, {
        "real_posts": real_posts,
        "master_start_row": master_start_row,
        "daily_start_row": daily_start_row,
        "dry_run": dry_run,
        "stats": stats.copy(),
        "cfg": cfg,
    })

    # ── Stage 7: Email Decision ────────────────────────────────────────
    real_posts = await run_email_decision(real_posts, emit)
    with_email = sum(1 for p in real_posts if p.get("_final_email"))
    no_email = len(real_posts) - with_email

    # ── Stage 8: Brevo Sending ─────────────────────────────────────────
    send_result = await run_brevo_sender(
        real_posts, master_ws, daily_ws, emit,
        daily_cap=sending.get("daily_email_cap", 100),
        delay_seconds=sending.get("email_send_delay_seconds", 2),
        dry_run=dry_run,
        excluded_domains=[d.lower().strip() for d in sending.get("excluded_domains", []) if d.strip()],
        reply_to=sending.get("reply_to_email", ""),
    )
    stats["sent"] = send_result["sent"]
    await emit({"event": "stats", **stats})

    # ── Stage 9: Finalize Sheets ───────────────────────────────────────
    await emit({"event": "stage_start", "stage": 9, "name": "Finalize Sheets",
                "message": "Writing final email and send statuses back to Sheets..."})
    await finalize_sheet_columns(master_ws, daily_ws, real_posts, master_start_row, daily_start_row)
    await emit({"event": "stage_complete", "stage": 9, "name": "Finalize Sheets",
                "metric": "Sheet updated"})

    # All done — clear checkpoint
    cp.clear()

    duration_min = round((time.time() - pipeline_start) / 60, 1)
    dry_tag = " [DRY RUN — no emails actually sent]" if dry_run else ""
    final_msg = (
        f"🎯 Pipeline complete — {send_result['sent']} emails sent, "
        f"{send_result['failed']} failed, {no_email} no email{dry_tag}"
    )
    await send_alert(final_msg)
    log.info(f"Pipeline finished in {duration_min} minutes")

    await emit({
        "event": "complete",
        "scraped": stats.get("scraped", 0),
        "real": stats.get("real", 0),
        "with_email": with_email,
        "sent": send_result["sent"],
        "failed": send_result["failed"],
        "no_email": no_email,
        "duration_min": duration_min,
        "dry_run": dry_run,
    })


async def run_pipeline_async(emit):
    from admin_config import load as load_cfg
    cfg = load_cfg()

    filtering = cfg.get("filtering", {})
    sending = cfg.get("sending", {})

    pipeline_start = time.time()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dry_run = sending.get("dry_run_mode", False)

    # Clear any existing checkpoint — fresh run
    cp.clear()

    await send_alert(f"🚀 Pipeline started — {ts}{' [DRY RUN]' if dry_run else ''}")
    log.info(f"Pipeline started at {ts} | dry_run={dry_run}")

    stats = {"scraped": 0, "real": 0, "enriched": 0, "sent": 0}

    try:
        # ── Stage 1: Apify ─────────────────────────────────────────────
        posts = await run_apify(emit, cfg)
        stats["scraped"] = len(posts)
        await emit({"event": "stats", **stats})
        await send_alert(f"✅ Stage 1 done — {len(posts)} posts scraped")

        excluded_kw = [k.lower() for k in filtering.get("excluded_keywords", []) if k.strip()]
        if excluded_kw:
            before = len(posts)
            posts = [
                p for p in posts
                if not any(kw in (p.get("text") or p.get("content") or "").lower() for kw in excluded_kw)
            ]
            if before != len(posts):
                log.info(f"Excluded keyword filter removed {before - len(posts)} posts")

        # ── Open Sheets ────────────────────────────────────────────────
        sh = await open_sheets(emit)
        try:
            master_ws_tmp = await asyncio.to_thread(sh.worksheet, "Master")
        except Exception:
            master_ws_tmp = await asyncio.to_thread(
                lambda: sh.add_worksheet(title="Master", rows=2000, cols=20)
            )

        # ── Stage 2: Deduplication + India Location Filter ──────────────
        new_posts, india_stats = await run_deduplication(posts, master_ws_tmp, emit)
        india_rejected = india_stats["rejected_no_india"] + india_stats["rejected_agency"]
        india_pass_rate = round(100 * india_stats["passed"] / india_stats["total"], 1) if india_stats["total"] else 0.0
        await send_alert(
            f"✅ Stage 2 done — {len(new_posts)} new leads, "
            f"India filter: {india_stats['passed']} passed / {india_rejected} rejected "
            f"({india_pass_rate}% pass rate)"
        )

        if not new_posts:
            await emit({"event": "complete", "scraped": stats["scraped"], "real": 0,
                        "with_email": 0, "sent": 0, "failed": 0, "no_email": 0,
                        "duration_min": round((time.time() - pipeline_start) / 60, 1)})
            await send_alert("✅ Pipeline complete — 0 new leads after dedup/India filter")
            return

        # ── Stage 3: GPT Filter ────────────────────────────────────────
        gpt_enabled = filtering.get("gpt_filter_enabled", True)
        if gpt_enabled:
            real_posts, skipped_posts = await run_gpt_filter(new_posts, emit)
        else:
            real_posts = new_posts
            skipped_posts = []
            for p in real_posts:
                p["_lead_status"] = "REAL"
            await emit({"event": "stage_start", "stage": 3, "name": "GPT Filter",
                        "message": "GPT filter disabled — passing all posts"})
            await emit({"event": "stage_complete", "stage": 3, "name": "GPT Filter",
                        "metric": f"Skipped (disabled) — {len(real_posts)} passed"})

        if filtering.get("only_posts_with_email"):
            real_posts = [p for p in real_posts if p.get("_email_in_post")]

        stats["real"] = len(real_posts)
        await emit({"event": "stats", **stats})
        await send_alert(f"✅ Stage 3 done — {len(real_posts)} real leads")

        if not real_posts:
            await run_sheets_writer([], skipped_posts, sh, emit, dry_run=dry_run)
            await emit({"event": "complete", "scraped": stats["scraped"], "real": 0,
                        "with_email": 0, "sent": 0, "failed": 0, "no_email": 0,
                        "duration_min": round((time.time() - pipeline_start) / 60, 1)})
            await send_alert("✅ Pipeline complete — 0 real leads found")
            return

        # ── Stage 4: GPT Classify ──────────────────────────────────────
        real_posts = await run_gpt_classify(real_posts, emit)
        await send_alert(f"✅ Stage 4 done — {len(real_posts)} leads classified")

        # Checkpoint after Stage 4 — expensive AI work done
        cp.save(4, {
            "real_posts": real_posts,
            "skipped_posts": skipped_posts,
            "dry_run": dry_run,
            "stats": stats.copy(),
            "cfg": cfg,
        })

        # ── Stage 5: Write to Sheets ───────────────────────────────────
        master_ws, daily_ws, all_posts, master_start_row, daily_start_row = await run_sheets_writer(
            real_posts, skipped_posts, sh, emit, dry_run=dry_run
        )
        await send_alert(f"✅ Stage 5 done — {len(all_posts)} rows written to Sheets")
        real_posts = all_posts[:len(real_posts)]

        # Checkpoint after Stage 5 — Sheets written, has tab/row info
        cp.save(5, {
            "real_posts": real_posts,
            "master_start_row": master_start_row,
            "daily_start_row": daily_start_row,
            "daily_tab": cp.load().get("daily_tab", "") if cp.exists() else "",
            "dry_run": dry_run,
            "stats": stats.copy(),
            "cfg": cfg,
        })

        # ── Stages 6–9 ─────────────────────────────────────────────────
        await _run_stages_6_to_9(
            emit, real_posts, master_ws, daily_ws,
            master_start_row, daily_start_row,
            cfg, dry_run, stats, pipeline_start,
        )

    except Exception as e:
        err_msg = str(e)
        log.error(f"Pipeline FAILED: {err_msg}", exc_info=True)
        await send_alert(f"❌ Pipeline FAILED: {err_msg[:200]}")
        await emit({"event": "error", "stage": 0, "message": err_msg})
        # Checkpoint is preserved on failure so resume is possible


async def resume_pipeline_async(emit):
    """Resume from the last saved checkpoint (Stage 4 or 5)."""
    state = cp.load()
    if not state:
        await emit({"event": "error", "stage": 0,
                    "message": "No checkpoint found. Please run the full pipeline."})
        return

    stage_completed = state.get("stage_completed", 0)
    pipeline_start = time.time()

    log.info(f"Resuming from Stage {stage_completed} checkpoint")
    await send_alert(f"🔄 Pipeline RESUMING from Stage {stage_completed} — {datetime.now().strftime('%H:%M:%S')}")

    # Replay completed stage events so frontend shows correct state
    for s in range(1, stage_completed + 1):
        await emit({
            "event": "stage_complete",
            "stage": s,
            "name": STAGE_NAMES.get(s, f"Stage {s}"),
            "metric": "Completed (from checkpoint)",
            "from_checkpoint": True,
        })

    stats = state.get("stats", {"scraped": 0, "real": 0, "enriched": 0, "sent": 0})
    await emit({"event": "stats", **stats})

    real_posts = state.get("real_posts", [])
    dry_run = state.get("dry_run", False)
    cfg = state.get("cfg", {})

    if not real_posts:
        await emit({"event": "error", "stage": stage_completed,
                    "message": "Checkpoint has no lead data to resume from."})
        return

    try:
        # Re-open Sheets connection
        sh = await open_sheets(emit)

        if stage_completed == 4:
            # Need to redo Stage 5 (Sheets write) then continue
            skipped_posts = state.get("skipped_posts", [])
            master_ws, daily_ws, all_posts, master_start_row, daily_start_row = await run_sheets_writer(
                real_posts, skipped_posts, sh, emit, dry_run=dry_run
            )
            real_posts = all_posts[:len(real_posts)]
            cp.save(5, {
                "real_posts": real_posts,
                "master_start_row": master_start_row,
                "daily_start_row": daily_start_row,
                "dry_run": dry_run,
                "stats": stats.copy(),
                "cfg": cfg,
            })

        elif stage_completed >= 5:
            # Stage 5 already done — just re-open the worksheets
            daily_tab = state.get("daily_tab", "")
            master_start_row = state.get("master_start_row")
            daily_start_row = state.get("daily_start_row", 2)

            master_ws = await asyncio.to_thread(
                lambda: sh.worksheet("Master") if not dry_run else sh.worksheets()[0]
            )
            if daily_tab:
                try:
                    daily_ws = await asyncio.to_thread(sh.worksheet, daily_tab)
                except Exception:
                    daily_ws = await asyncio.to_thread(
                        lambda: sh.add_worksheet(title=daily_tab, rows=2000, cols=20)
                    )
            else:
                daily_ws = master_ws
        else:
            await emit({"event": "error", "stage": stage_completed,
                        "message": f"Cannot resume from Stage {stage_completed}. Please run a fresh pipeline."})
            return

        # Continue from Stage 6 onwards
        await _run_stages_6_to_9(
            emit, real_posts, master_ws, daily_ws,
            master_start_row, daily_start_row,
            cfg, dry_run, stats, pipeline_start,
        )

    except Exception as e:
        err_msg = str(e)
        log.error(f"Resume FAILED: {err_msg}", exc_info=True)
        await send_alert(f"❌ Resume FAILED: {err_msg[:200]}")
        await emit({"event": "error", "stage": stage_completed, "message": err_msg})
