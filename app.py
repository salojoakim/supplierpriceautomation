"""
Main pipeline (now using utils.price_analyzer for snapshot + diff).

What it does:
- Reads .eml from EMAIL_DIR_DEFAULT or, if USE_GRAPH=true, fetches to INBOX_TODAY_DIR via Microsoft Graph.
- For each email: body -> LLM; attachments -> attachment_parser; PDF/DOCX text -> LLM.
- Builds today's normalized rows.
- Uses utils.price_analyzer to:
    * load previous (logs/latest.json)
    * compare current vs previous (changed/new/removed)
    * save today's snapshot (logs/parsed_YYYY-MM-DD.json) and update latest.json
- Adapts the diff shape to this file's render_diff_html() and sends the HTML via utils.mailer.

Run:
    python app.py

Notes:
- We keep your render_diff_html() table format.
- Unchanged pairs are not tracked by price_analyzer; we set unchanged_count=0.
- Toggle Graph with USE_GRAPH in .env (MS_* required).
"""

import os
import json
from datetime import datetime, date
from typing import List, Dict

from html import escape

from utils.email_reader import iter_eml_messages
from utils.attachment_parser import parse_attachments
from llm.extractor import extract_sms_prices_llm
from utils.mailer import send_email
from utils.graph_mail import fetch_shared_mailbox_to_folder

# NEW: centralized snapshot + diff helpers
from utils.price_analyzer import (
    load_previous_prices,
    save_current_prices,
    compare_prices,
)

# ---------- Konfig ----------
EMAIL_DIR_DEFAULT = "data/email_memory"
INBOX_TODAY_DIR = "data/inbox_today"
LOG_DIR = "logs"

TODAY = date.today().isoformat()
SNAPSHOT_PATH = os.path.join(LOG_DIR, f"parsed_{TODAY}.json")
LATEST_PATH = os.path.join(LOG_DIR, "latest.json")


# ---------- Extrahera ----------
def process_dir(email_dir: str) -> List[Dict]:
    """
    Går igenom alla .eml i en katalog och extraherar normaliserade prisrader.
    - Mailkropp -> LLM
    - Bilagor: Excel/CSV -> rader direkt; PDF/DOCX -> textblock -> LLM
    """
    rows: List[Dict] = []
    if not os.path.isdir(email_dir):
        print(f"❌ Hittar inte katalogen: {email_dir}")
        return rows

    for msg in iter_eml_messages(email_dir):
        filename = msg["filename"]
        body = msg["body"]
        attachments = msg["attachments"]

        print(f"\n📨 Behandlar: {filename}")
        provider_hint = os.path.splitext(filename)[0]

        # 1) Kropp -> LLM
        if body and body.strip():
            rows.extend(extract_sms_prices_llm(email_text=body, provider_hint=provider_hint))

        # 2) Bilagor
        if attachments:
            parsed = parse_attachments(attachments, provider_hint=provider_hint)
            rows.extend(parsed["rows"])  # Excel/CSV redan strukturerat
            for blob in parsed["texts"]:  # PDF/DOCX -> LLM
                rows.extend(extract_sms_prices_llm(email_text=blob, provider_hint=provider_hint))

    return rows


# ---------- Mailrender ----------
def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6f}"
    # escape to avoid accidental HTML injection from supplier text
    return escape(str(v))


def render_diff_html(diff: Dict[str, List[Dict]]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    changed = diff["changed"]; new = diff["new"]; removed = diff["removed"]; unchanged_count = diff["unchanged_count"]

    def row_from(rec, old, newv, direction):
        r = rec or {}
        return f"""
        <tr>
          <td>{_fmt(r.get('provider'))}</td>
          <td>{_fmt(r.get('country'))}</td>
          <td>{_fmt(r.get('network') or r.get('operator'))}</td>
          <td>{_fmt(r.get('mcc'))}</td>
          <td>{_fmt(r.get('mnc'))}</td>
          <td style="text-align:right">{_fmt(old)}</td>
          <td style="text-align:right">{_fmt(newv)}</td>
          <td>{_fmt(r.get('currency'))}</td>
          <td>{_fmt(r.get('effective_from'))}</td>
          <td>{_fmt(direction)}</td>
        </tr>"""

    changed_rows = "\n".join([row_from(c["today"] or c["prev"], c["old"], c["new"], c["direction"]) for c in changed]) or '<tr><td colspan="10">No changes</td></tr>'
    new_rows = "\n".join([row_from(n["today"], n["old"], n["new"], "new") for n in new]) or '<tr><td colspan="10">No new entries</td></tr>'
    removed_rows = "\n".join([row_from(r["prev"], r["old"], r["new"], "removed") for r in removed]) or '<tr><td colspan="10">No removed entries</td></tr>'

    style = """
    <style>
      body {font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;}
      table {border-collapse: collapse; width: 100%;}
      th, td {border: 1px solid #ddd; padding: 6px; font-size: 12px;}
      th {background: #f5f5f5; text-align: left;}
      h2 {margin: 18px 0 6px;}
      .small {color: #666; font-size: 12px;}
    </style>"""
    html = f"""
    <html><head>{style}</head><body>
      <h1>SMS Price Daily Summary – {TODAY}</h1>
      <p class="small">Generated {ts}</p>
      <p><b>Summary:</b> Changed: {len(changed)} · New: {len(new)} · Removed: {len(removed)} · Unchanged pairs: {unchanged_count}</p>

      <h2>Changed</h2>
      <table><thead><tr>
        <th>Provider</th><th>Country</th><th>Network/Operator</th><th>MCC</th><th>MNC</th>
        <th>Old</th><th>New</th><th>Currency</th><th>Effective From</th><th>Direction</th>
      </tr></thead><tbody>{changed_rows}</tbody></table>

      <h2>New entries</h2>
      <table><thead><tr>
        <th>Provider</th><th>Country</th><th>Network/Operator</th><th>MCC</th><th>MNC</th>
        <th>Old</th><th>New</th><th>Currency</th><th>Effective From</th><th>Direction</th>
      </tr></thead><tbody>{new_rows}</tbody></table>

      <h2>Removed entries</h2>
      <table><thead><tr>
        <th>Provider</th><th>Country</th><th>Network/Operator</th><th>MCC</th><th>MNC</th>
        <th>Old</th><th>New</th><th>Currency</th><th>Effective From</th><th>Direction</th>
      </tr></thead><tbody>{removed_rows}</tbody></table>
    </body></html>"""
    return html


# ---------- MAIN ----------
def main():
    use_graph = os.getenv("USE_GRAPH", "false").lower() in ("1", "true", "yes")

    # Om Graph är på: hämta dagens mail till tempkatalog
    email_dir = EMAIL_DIR_DEFAULT
    if use_graph:
        tenant = os.getenv("MS_TENANT_ID", "")
        client_id = os.getenv("MS_CLIENT_ID", "")
        client_secret = os.getenv("MS_CLIENT_SECRET", "")
        shared_mailbox = os.getenv("MS_SHARED_MAILBOX", "")
        if not all([tenant, client_id, client_secret, shared_mailbox]):
            raise RuntimeError("Saknar MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET / MS_SHARED_MAILBOX i .env")

        print("☁️  Hämtar mail från shared mailbox via Microsoft Graph...")
        saved = fetch_shared_mailbox_to_folder(
            tenant_id=tenant,
            client_id=client_id,
            client_secret=client_secret,
            shared_mailbox=shared_mailbox,
            dest_folder=INBOX_TODAY_DIR,
            days_back=int(os.getenv("MS_DAYS_BACK", "1")),
            mail_folder=os.getenv("MS_MAIL_FOLDER", "Inbox"),
            clear_dest_first=True,
            top=int(os.getenv("MS_TOP", "100")),
        )
        print(f"✔️  Sparade {len(saved)} .eml i {INBOX_TODAY_DIR}")
        email_dir = INBOX_TODAY_DIR

    # Kör extraktion
    today_rows = process_dir(email_dir)
    if not today_rows:
        print("⚠️ Inget extraherat idag – avbryter mail.")
        return

    # --- Snapshot + diff using utils.price_analyzer ---
    os.makedirs(LOG_DIR, exist_ok=True)

    # 1) Load previous (latest.json if present)
    prev_rows = load_previous_prices(LATEST_PATH)

    # 2) Compare current vs previous
    diff_core = compare_prices(today_rows, prev_rows)
    # diff_core = {"changed":[{"before":..,"after":..,"delta":..},...],
    #              "new":[...], "removed":[...], "summary":{"changed":N,"new":M,"removed":K}}

    # 3) Save today's snapshot (also updates logs/latest.json)
    save_current_prices(today_rows, SNAPSHOT_PATH)

    # --- Adapt diff to this file's render_diff_html() shape ---
    def _price_any(rec):
        if not isinstance(rec, dict):
            return None
        for k in ("new_price", "price", "rate", "current_rate", "previous_rate", "old_price"):
            v = rec.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None

    changed_adapted = []
    for c in diff_core["changed"]:
        before, after = c.get("before"), c.get("after")
        old = _price_any(before)
        newv = _price_any(after)
        direction = "increase" if (old is not None and newv is not None and newv > old) else \
                    "decrease" if (old is not None and newv is not None and newv < old) else "changed"
        changed_adapted.append({
            "key": None,
            "today": after,
            "prev": before,
            "old": old,
            "new": newv,
            "delta": c.get("delta"),
            "direction": direction,
        })

    new_adapted = [{
        "key": None,
        "today": n,
        "prev": None,
        "old": None,
        "new": _price_any(n),
        "delta": None,
        "direction": "new",
    } for n in diff_core["new"]]

    removed_adapted = [{
        "key": None,
        "today": None,
        "prev": r,
        "old": _price_any(r),
        "new": None,
        "delta": None,
        "direction": "removed",
    } for r in diff_core["removed"]]

    diff = {
        "changed": changed_adapted,
        "new": new_adapted,
        "removed": removed_adapted,
        "unchanged_count": 0,  # not tracked by price_analyzer; set to 0
    }

    # HTML + send
    html = render_diff_html(diff)
    subject = f"SMS Price Summary {TODAY} – Changed:{len(diff['changed'])} New:{len(diff['new'])} Removed:{len(diff['removed'])}"
    send_email(subject=subject, html_body=html)
    print("\n📤 Daglig summering skickad.")


if __name__ == "__main__":
    main()
