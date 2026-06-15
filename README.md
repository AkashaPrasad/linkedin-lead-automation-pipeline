# LinkedIn Lead Automation Pipeline

> A full-stack outbound automation platform built for Decision Pinnacle — scrapes LinkedIn posts, qualifies leads with AI, enriches emails, and sends personalised outreach. One button, fully automated.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=flat&logo=tailwindcss&logoColor=white)

---

## Overview

This pipeline automates the entire LinkedIn outbound workflow:

1. **Scrape** — pulls recent LinkedIn posts matching configurable marketing keywords via Apify
2. **Deduplicate** — skips leads already present in the Google Sheets master log
3. **AI Filter** — uses Gemini to discard false positives (freelancers, job seekers, recruiters)
4. **AI Classify** — extracts emails from post text, classifies each lead into a marketing category
5. **Log to Sheets** — writes every lead to a persistent Master tab and a dated daily tab
6. **Enrich** — looks up missing emails via Apollo.io
7. **Send** — fires personalised category-specific emails through Brevo with configurable daily caps
8. **Finalise** — writes send status, timestamps, and error details back to the sheet

The React dashboard streams live progress over SSE so you can watch each stage complete in real time.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Real-time streaming | Server-Sent Events (SSE) |
| AI filtering & classification | Google Gemini 1.5 Flash |
| LinkedIn scraping | Apify (`harvestapi~linkedin-post-search`) |
| Email enrichment | Apollo.io Bulk Match API |
| Email delivery | Brevo transactional API |
| Lead storage | Google Sheets via gspread |
| Alerts | Telegram Bot |
| Frontend | React 18 + Vite + Tailwind CSS |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- Accounts with API access: Apify, Gemini (Google AI Studio), Apollo.io, Brevo, Google Cloud (service account), Telegram

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/AkashaPrasad/linkedin-lead-automation-pipeline.git
cd linkedin-lead-automation-pipeline
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Open .env and fill in all values
```

### 3. Add Google service account

Place your `service_account.json` file inside the `backend/` directory. The service account must have Editor access to the target Google Sheet.

```
backend/
└── service_account.json   ← paste here
```

### 4. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 5. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running the App

**Terminal 1 — Backend**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) and press **Run Pipeline**.

## Railway Deployment Note

If a Railway-provided `*.up.railway.app` URL opens for some networks but fails with `ERR_NAME_NOT_RESOLVED` on others, the app may be healthy and the problem may be ISP DNS resolution for Railway subdomains. In production, prefer attaching a custom domain such as `pipeline.yourdomain.com` instead of relying on the default Railway hostname.

If you must test the Railway hostname directly, verify that:
- the service has **Networking -> Public Networking** enabled
- the generated Railway domain is attached to the correct service
- a custom domain's `CNAME` and `TXT` records exactly match Railway's dashboard values

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `APIFY_API_TOKEN` | Yes | From console.apify.com → Settings → Integrations |
| `APIFY_ACTOR_ID` | Yes | Default: `harvestapi~linkedin-post-search` |
| `GEMINI_API_KEY` | Yes | From aistudio.google.com |
| `OPENAI_API_KEY` | Optional | Falls back to Gemini if not set |
| `APOLLO_API_KEY` | Yes | From apollo.io → Settings → API |
| `BREVO_API_KEY` | Yes | From brevo.com → Account → API Keys |
| `BREVO_SENDER_EMAIL` | Yes | Verified sender email in Brevo |
| `BREVO_SENDER_NAME` | Yes | Display name (e.g. `Decision Pinnacle`) |
| `GOOGLE_SHEET_ID` | Yes | From the Google Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Yes | Filename only — defaults to `service_account.json` |
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Yes | Group chat ID (negative number) |
| `MAX_EMAILS_PER_RUN` | Optional | Hard cap per run (default: 100) |
| `APIFY_MAX_POSTS` | Optional | Max posts to scrape per run (default: 500) |
| `DAILY_EMAIL_CAP` | Optional | Daily send limit (default: 100) |

### Google Sheets Setup

1. Create a new Google Sheet
2. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`
3. Share the sheet with your service account email (Editor access):
   ```
   pipeline-bot@<your-project>.iam.gserviceaccount.com
   ```

The pipeline auto-creates two tabs on first run:
- **Master** — cumulative record of all leads ever processed
- **DD-Mon-YYYY** — daily tab for each run

**Sheet columns:** Post Content · Post URL · Author Name · LinkedIn URL · Author Headline · Posted Date · Email From Post · Apollo Email · Final Email · Has Email · Category · Lead Status · Template Sent · Sent Status · Sent Timestamp · Error

---

## Pipeline Stages

| # | Stage | Tool | What it does |
|---|---|---|---|
| 1 | Apify Scraper | Apify | Scrapes LinkedIn posts by configurable keyword queries |
| 2 | Deduplication | Google Sheets | Skips profiles already logged in the Master tab |
| 3 | AI Filter | Gemini | Removes false leads — freelancers, recruiters, job posts |
| 4 | AI Classify | Gemini | Extracts emails from post text, assigns marketing category |
| 5 | Sheets Writer | gspread | Logs all leads to Master + daily tab |
| 6 | Apollo Enrichment | Apollo.io | Looks up emails for leads missing one |
| 7 | Email Decision | — | Picks best email: post > Apollo |
| 8 | Email Sender | Brevo | Sends personalised email per category |
| 9 | Finalize Sheets | gspread | Writes send status, timestamps, errors back to sheet |

---

## Email Categories

The AI classifier assigns each lead one of six categories. A matching template is sent automatically.

| Category | Triggered by |
|---|---|
| **Growth** | Performance marketing, Meta/Google ads, ROAS, D2C scaling, marketplace |
| **Branding** | Brand identity, strategy, rebranding, visual identity |
| **Creative & Campaign** | Ad films, TVC, UGC, influencer, video production |
| **Social Media** | Instagram management, reels, content calendar, organic social |
| **Marketplace** | Amazon, Flipkart, quick-commerce, listing optimisation |
| **Generic** | General need, unclear context, or multiple services equally relevant |

Templates are editable from the dashboard without touching code.

---

## Admin Controls

The pipeline ships with a configurable admin panel accessible from the dashboard:

- **Scraping** — keyword queries, post cap, time window, geography, industry filters
- **Filtering** — toggle AI filter, exclude keywords, language filter
- **Enrichment** — toggle Apollo, set per-run enrichment limit
- **Sending** — daily cap, send delay, dry-run mode, excluded domains, reply-to address

**Dry-run mode** (on by default) logs everything to Sheets but skips actual email delivery — safe for testing.

---

## Checkpoint & Resume

If the pipeline fails mid-run (e.g. a network timeout after Apollo enrichment), it saves a checkpoint. On the next run you can press **Resume** in the dashboard to continue from where it left off instead of re-running the expensive scraping and AI stages.

---

## Project Structure

```
.
├── backend/
│   ├── main.py                  # FastAPI app, SSE streaming, all API routes
│   ├── pipeline.py              # Pipeline orchestrator — calls each stage in order
│   ├── checkpoint.py            # Save/load/clear mid-run checkpoints
│   ├── config.py                # Env var loading and validation
│   ├── logger.py                # Structured logging
│   ├── admin_config.py          # Admin config read/write helpers
│   ├── post_fields.py           # Shared field key constants
│   ├── requirements.txt
│   ├── stages/
│   │   ├── apify_scraper.py     # Stage 1
│   │   ├── deduplication.py     # Stage 2
│   │   ├── gpt_filter.py        # Stage 3
│   │   ├── gpt_classify.py      # Stage 4
│   │   ├── sheets_writer.py     # Stage 5
│   │   ├── apollo_enricher.py   # Stage 6
│   │   ├── email_decision.py    # Stage 7
│   │   ├── brevo_sender.py      # Stage 8
│   │   └── alerts.py            # Telegram notifications
│   └── templates/               # Category email templates (Python modules)
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Root component, SSE client
│   │   └── components/
│   │       └── PipelineRunner.jsx
│   ├── package.json
│   └── vite.config.js
├── templates.json               # User-edited email templates (overrides Python defaults)
├── admin_config.json            # Persisted admin configuration
├── .env.example                 # Environment variable template
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
