# supplierpriceautomation

# sms_price

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
│
│ (optional) Microsoft Graph → .eml in data/inbox_today/
▼
[Parsers] Body → LLM | Attachments → (CSV/Excel deterministic, PDF/DOCX via LLM)
▼
[Normalized rows]
▼
[Snapshot (JSON)] + [Diff vs. previous]
▼
[HTML report via SMTP] (or saved in logs/outbox if DRY_RUN)


## Project Structure
sms_price/
app.py # main pipeline
requirements.txt
.env.example # template (no secrets)
utils/
email_reader.py # read .eml (body + attachments)
attachment_parser.py # CSV/Excel/PDF/DOCX handling
mailer.py # send or save HTML report
graph_mail.py # Microsoft Graph (shared mailbox) fetch
llm/
extractor.py # Gemini + mock-mode
prompt_templates.py # LLM prompt
data/ # local emails & archive (git-ignored)
logs/ # snapshots & outbox (git-ignored)



> `.gitignore` excludes: `.venv/`, `data/`, `logs/`, `.env`, editor folders, etc. Keep `.gitkeep` files in `data/` and `logs/` so folders exist in the repo.

---

## Prerequisites
- **Python 3.10+**
- Gemini **API key** if running real LLM (not needed in mock mode)
- An SMTP account to send the daily report (skip when `DRY_RUN=true`)
- (Optional) Azure App with **Microsoft Graph** if reading a shared mailbox

---

## Install

```bash
# Create & activate a venv (Windows PowerShell)
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# macOS/Linux
# python -m venv .venv
# source .venv/bin/activate

pip install -r requirements.txt
