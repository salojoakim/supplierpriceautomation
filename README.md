# supplierpriceautomation

Automated pipeline that ingests **provider emails** about SMS pricing (both **email body** and **attachments**), extracts and normalizes price rows, stores a **daily snapshot**, diffs against the **previous snapshot**, and sends a **daily HTML summary**.

- **Sources:** local `.eml` files or a Microsoft 365 **shared mailbox** via **Microsoft Graph**
- **Attachments:** Excel/CSV (deterministic parsing), PDF/DOCX (LLM-based)
- **LLM:** Google **Gemini** (`google-generativeai`) or **mock mode** (no API cost)
- **Output:** daily HTML report + JSON snapshots

---

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Configuration (.env)](#configuration-env)
- [Quick Start – Simulation (no cloud needed)](#quick-start--simulation-no-cloud-needed)
- [Production](#production)
- [Schedule a Daily Run](#schedule-a-daily-run)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [License](#license)

---

## Features
- Read **.eml** locally or pull emails from a **shared mailbox** (Microsoft Graph).
- Extract pricing from **body text** (LLM) and **attachments**:
  - Excel/CSV → column-based parsing (`Country`, `MCC`, `MNC`, `Rate(EUR)`, `Currency`, …)
  - PDF/DOCX → text extraction + LLM
- Store daily **snapshots** (`logs/parsed_YYYY-MM-DD.json` + `logs/latest.json`).
- Diff vs. previous snapshot: **Changed / New / Removed**.
- Email a **rich HTML report** (or save the HTML when `DRY_RUN=true`).

---

## Architecture
    [Email (.EML or Shared Mailbox)]
       |
       |-- (optional) Microsoft Graph --> .eml in data/inbox_today/
       v
    [Parsers]  Body -> LLM  |  Attachments -> (CSV/Excel deterministic, PDF/DOCX via LLM)
       v
    [Normalized rows]
       v
    [Snapshot (JSON)]  +  [Diff vs previous]
       v
    [HTML report via SMTP]  (or saved in logs/outbox if DRY_RUN)

---

## Project Structure
    supplierpriceautomation/
    ├─ app.py
    ├─ requirements.txt
    ├─ README.md
    ├─ .env.example
    ├─ utils/
    │  ├─ email_reader.py        # read .eml (body + attachments)
    │  ├─ attachment_parser.py   # CSV/Excel/PDF/DOCX handling
    │  ├─ mailer.py              # send or save HTML report
    │  └─ graph_mail.py          # Microsoft Graph (shared mailbox) fetch
    ├─ llm/
    │  ├─ extractor.py           # Gemini + mock-mode
    │  └─ prompt_templates.py    # LLM prompt
    ├─ tests/                    # optional tests
    ├─ data/                     # local emails & archive (git-ignored)
    └─ logs/                     # snapshots & outbox (git-ignored)

> `.gitignore` excludes: `.venv/`, `data/`, `logs/`, `.env`, editor folders, etc.  
> Keep `.gitkeep` files in `data/` and `logs/` so folders remain in the repo.

---

## Prerequisites
- **Python 3.10+**
- Gemini **API key** if running real LLM (not needed in mock mode)
- SMTP account for the daily report (skip when `DRY_RUN=true`)
- (Optional) Azure App with **Microsoft Graph** (Application permission **Mail.Read**) if reading a shared mailbox

---

## Install
    # Windows (CMD)
    py -m venv .venv
    .\.venv\Scripts\activate.bat
    pip install -U pip
    pip install -r requirements.txt

    # macOS/Linux
    # python -m venv .venv
    # source .venv/bin/activate
    # pip install -U pip
    # pip install -r requirements.txt

---

## Configuration (.env)
Copy `.env.example` → `.env` and fill in values (never commit `.env`):

    # Modes
    USE_GRAPH=false
    MOCK_LLM=true
    DRY_RUN=true

    # Microsoft Graph (only if USE_GRAPH=true)
    MS_TENANT_ID=
    MS_CLIENT_ID=
    MS_CLIENT_SECRET=
    MS_SHARED_MAILBOX=
    MS_MAIL_FOLDER=Inbox
    MS_DAYS_BACK=1
    MS_TOP=100

    # Gemini (only if MOCK_LLM=false)
    GOOGLE_API_KEY=

    # SMTP (only if DRY_RUN=false)
    SMTP_HOST=
    SMTP_PORT=587
    SMTP_USER=
    SMTP_PASSWORD=
    SMTP_FROM=
    SMTP_TO=
    SMTP_STARTTLS=true

Tips:
- Put secrets in quotes if they contain special characters.
- Don’t add inline comments on the same line as values.

---

## Quick Start – Simulation (no cloud needed)
1) Put a few `.eml` files in `data/email_memory/`  
   (Outlook → Save As → file type **.eml**)
2) In `.env`:
    - `USE_GRAPH=false`
    - `MOCK_LLM=true`
    - `DRY_RUN=true`
3) Run:
    - `python app.py`
4) Open the HTML report in `logs/outbox/summary_*.html`.

---

## Production
1) **Real LLM:** set `MOCK_LLM=false` and add `GOOGLE_API_KEY`.  
2) **Send emails:** set `DRY_RUN=false` and fill SMTP settings.  
3) **Shared mailbox (Graph):**
   - Install `msal` + `requests`
   - Azure App with **Mail.Read (Application)** + admin consent
   - Fill MS_* values and set `USE_GRAPH=true`

Run:
    python app.py

---

## Schedule a Daily Run
**Windows Task Scheduler**
    @echo off
    cd /d C:\path\to\supplierpriceautomation
    call .venv\Scripts\activate
    python app.py

**Linux/macOS (cron)**
    0 7 * * * /path/to/.venv/bin/python /path/to/supplierpriceautomation/app.py >> /path/to/logs/cron.log 2>&1

---

## Testing
    pip install pytest
    pytest -q

---

## Troubleshooting
- `ModuleNotFoundError: msal` → install `msal` or set `USE_GRAPH=false`.  
- No email sent → ensure `DRY_RUN=false` and SMTP values are correct (in `DRY_RUN=true` the HTML is saved to `logs/outbox`).  
- PDF/DOCX not parsed → mock mode is simplified; use `MOCK_LLM=false` for LLM parsing.  
- Excel/CSV columns differ → extend `attachment_parser.py` or let LLM handle tricky layouts.

---

## Security
- `.env` is git-ignored; never commit secrets.
- Limit Azure app to **Mail.Read (Application)**.
- Handle snapshots/logs per company policy (may include pricing data).

---

## License
MIT (or your preferred license)
