import asyncio
import time
from datetime import datetime
from logger import get_logger
from stages.alerts import send_alert
from stages.apify_scraper import run_apify
from stages.deduplication import run_deduplication
from stages.gpt_filter import run_gpt_filter
from stages.gpt_classify import run_gpt_classify
from stages.repeat_lead_filter import check_repeat_leads
from stages.sheets_writer import open_sheets, run_sheets_writer, finalize_sheet_columns, append_sent_to_master
from stages.apollo_enricher import run_apollo_enricher
from stages.email_decision import run_email_decision
from stages.brevo_sender import run_brevo_sender
from stages.manual_leads import sync_sent_to_master, append_manual_leads
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

    # Checkpoint immediately after Brevo actually sends — real_posts now
    # carries each post's true _sent_status ("SENT"/"NO_EMAIL"). If Stage 9
    # below fails (e.g. a transient Sheets API error) and the run is later
    # resumed, this is what stops brevo_sender's idempotency guard from
    # ever re-sending an email that already went out.
    cp.save(8, {
        "real_posts": real_posts,
        "master_start_row": master_start_row,
        "daily_start_row": daily_start_row,
        "daily_tab": daily_ws.title,
        "dry_run": dry_run,
        "stats": stats.copy(),
        "cfg": cfg,
    })

    # ── Stage 9: Finalize Sheets ───────────────────────────────────────
    await emit({"event": "stage_start", "stage": 9, "name": "Finalize Sheets",
                "message": "Writing final email and send statuses back to Sheets..."})
    await finalize_sheet_columns(daily_ws, real_posts, daily_start_row)

    # Master only ever receives leads Stage 8 actually SENT an email to —
    # nothing skipped, nothing real-but-no-email. See append_sent_to_master.
    master_sent_count = await append_sent_to_master(master_ws, real_posts)

    # Real leads that never got an email (Apollo + post both came up empty,
    # or the send itself failed) still deserve outreach — via a manual
    # LinkedIn DM. Written to a separate sheet for a human to work through;
    # never done for dry runs, matching Master's own real-sends-only rule.
    manual_count = 0
    if not dry_run:
        manual_count = await append_manual_leads(real_posts, emit)

    await emit({"event": "stage_complete", "stage": 9, "name": "Finalize Sheets",
                "metric": f"Sheet updated — {master_sent_count} SENT leads added to Master, {manual_count} to Manual Leads"})

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


async def run_pipeline_async(emit, query_set_override: str | None = None):
    from admin_config import load as load_cfg
    cfg = load_cfg()

    # A scheduled run can pin a specific saved query folder to its time slot
    # (Admin Panel → Automation) instead of using whatever's currently the
    # active/default list. Swap it in before Stage 1 even starts. Manual runs
    # and runs with no override (query_set_override=None) are completely
    # unaffected — this only ever changes scraping.search_queries in memory
    # for THIS run, never persists back to admin_config.json.
    if query_set_override:
        query_sets = cfg.get("scraping", {}).get("query_sets", {})
        override_queries = query_sets.get(query_set_override)
        if override_queries:
            cfg = {**cfg, "scraping": {**cfg.get("scraping", {}), "search_queries": list(override_queries)}}
            log.info(f"Scheduled run: using query folder '{query_set_override}' ({len(override_queries)} queries)")
            await send_alert(f"📁 Using query folder '{query_set_override}' for this run ({len(override_queries)} queries)")
        else:
            log.warning(
                f"Scheduled run: query folder '{query_set_override}' not found "
                f"(may have been renamed/deleted) — falling back to the default query list"
            )
            await send_alert(
                f"⚠ Scheduled query folder '{query_set_override}' no longer exists — "
                f"using the default query list instead"
            )

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
        # ── Open Sheets (moved ahead of Stage 1 so the manual-leads sync
        # below can run before any scraping starts) ────────────────────
        sh = await open_sheets(emit)
        try:
            master_ws_tmp = await asyncio.to_thread(sh.worksheet, "Master")
        except Exception:
            from stages.sheets_writer import HEADERS as _HEADERS
            master_ws_tmp = await asyncio.to_thread(
                lambda: sh.add_worksheet(title="Master", rows=2000, cols=len(_HEADERS))
            )

        # Before every real run: pull in any lead a human has marked "Sent"
        # in the Manual Leads (LinkedIn DM) sheet since the last run, and
        # record it in Master — exactly like a successful email send. Never
        # blocks the run itself if the manual sheet is unreachable.
        synced = await sync_sent_to_master(master_ws_tmp, emit)
        if synced:
            await send_alert(f"✅ Synced {synced} manually-sent LinkedIn DM leads to Master")

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

        # ── Stage 2: Deduplication ───────────────────────────────────────
        new_posts = await run_deduplication(posts, master_ws_tmp, emit)

        if not new_posts:
            await emit({"event": "complete", "scraped": stats["scraped"], "real": 0,
                        "with_email": 0, "sent": 0, "failed": 0, "no_email": 0,
                        "duration_min": round((time.time() - pipeline_start) / 60, 1)})
            await send_alert("✅ Pipeline complete — 0 new leads (all duplicates)")
            return

        # ── Stage 3: GPT Filter ────────────────────────────────────────
        # All deduplicated posts go through the AI filter — nothing is
        # pre-rejected by location before this point.
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

        ai_filter_kept = len(real_posts)

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

        # Repeat lead check — runs now that we know each post's category.
        # Same author + same category already contacted = true duplicate ask,
        # held back. Same author + a DIFFERENT category (e.g. previously
        # asked about AI video generation, now asking about performance
        # marketing) = a genuinely new opportunity, kept and flagged so it's
        # visible as a repeat contact rather than being silently merged in.
        real_posts, repeat_duplicates, repeat_stats = await check_repeat_leads(real_posts, master_ws_tmp, emit)
        skipped_posts = skipped_posts + repeat_duplicates
        if repeat_stats["total"]:
            await send_alert(
                f"✅ Repeat lead check — {repeat_stats['new_authors']} new, "
                f"{repeat_stats['repeat_new_ask']} repeat contacts with a new ask, "
                f"{repeat_stats['duplicate_same_ask']} duplicate asks held back"
            )
        stats["real"] = len(real_posts)
        await emit({"event": "stats", **stats})

        # Full funnel in one line — every stage that can shrink the real-lead
        # count is summarized here, so "N kept" from an earlier stage never
        # looks inconsistent with the sheet's final real-lead total again.
        await emit({
            "event": "progress",
            "stage": 4,
            "message": (
                f"Funnel: {ai_filter_kept} AI-kept → "
                f"{len(real_posts)} final real leads (after repeat-lead dedup)"
            ),
        })

        if not real_posts:
            await run_sheets_writer([], skipped_posts, sh, emit, dry_run=dry_run)
            await emit({"event": "complete", "scraped": stats["scraped"], "real": 0,
                        "with_email": 0, "sent": 0, "failed": 0, "no_email": 0,
                        "duration_min": round((time.time() - pipeline_start) / 60, 1)})
            await send_alert("✅ Pipeline complete — 0 real leads found (all were duplicate asks)")
            return

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

        # Checkpoint after Stage 5 — Sheets written, has tab/row info.
        # daily_ws.title is the ACTUAL tab name Stage 5 just wrote to — not
        # a re-read of the previous (Stage 4) checkpoint, which never had
        # this key and would silently save an empty string here. An empty
        # daily_tab on a later resume makes resume_pipeline_async fall back
        # to using Master itself as the "daily" worksheet, corrupting real
        # Master rows with Stage 9 finalize writes aimed at the wrong tab.
        cp.save(5, {
            "real_posts": real_posts,
            "master_start_row": master_start_row,
            "daily_start_row": daily_start_row,
            "daily_tab": daily_ws.title,
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
                "daily_tab": daily_ws.title,
                "dry_run": dry_run,
                "stats": stats.copy(),
                "cfg": cfg,
            })

        elif stage_completed >= 5:
            # Stage 5 already done — just re-open the worksheets
            daily_tab = state.get("daily_tab", "")
            master_start_row = state.get("master_start_row")
            daily_start_row = state.get("daily_start_row", 2)

            master_ws = await asyncio.to_thread(sh.worksheet, "Master")
            if daily_tab:
                try:
                    daily_ws = await asyncio.to_thread(sh.worksheet, daily_tab)
                except Exception:
                    from stages.sheets_writer import HEADERS as _HEADERS
                    daily_ws = await asyncio.to_thread(
                        lambda: sh.add_worksheet(title=daily_tab, rows=2000, cols=len(_HEADERS))
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
