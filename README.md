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
