"""
Main pipeline.

What it does:
- Reads .eml from EMAIL_DIR_DEFAULT or, if USE_GRAPH=true, fetches to INBOX_TODAY_DIR via Microsoft Graph.
- For each email: body -> LLM; attachments -> attachment_parser; PDF/DOCX text -> LLM.
- Builds today's normalized rows.
- Saves snapshots to logs/parsed_YYYY-MM-DD.json and logs/latest.json.
- Computes diff vs previous snapshot using helpers in THIS file:
    find_previous_snapshot / load_snapshot / diff_snapshots
- Renders an HTML summary (render_diff_html) and sends via utils.mailer.send_email.

Run:
    python app.py

Notes:
- Diff identity key is KEY_FIELDS.
- Price selection via _pick_new_price/_pick_old_price.
- Toggle Graph with USE_GRAPH in .env (MS_* required).
"""


import os
import json
import glob
from datetime import datetime, date
from typing import List, Dict, Tuple

from utils.email_reader import iter_eml_messages
from utils.attachment_parser import parse_attachments
from llm.extractor import extract_sms_prices_llm
from utils.mailer import send_email
from utils.graph_mail import fetch_shared_mailbox_to_folder

# ---------- Konfig ----------
EMAIL_DIR_DEFAULT = "data/email_memory"
INBOX_TODAY_DIR = "data/inbox_today"
LOG_DIR = "logs"

TODAY = date.today().isoformat()
SNAPSHOT_PATH = os.path.join(LOG_DIR, f"parsed_{TODAY}.json")
LATEST_PATH = os.path.join(LOG_DIR, "latest.json")


# ---------- Extrahera ----------
def process_dir(email_dir: str) -> List[Dict]:
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


# ---------- Snapshot/Diff ----------
def save_snapshot(rows: List[Dict], path: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

def load_snapshot(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_previous_snapshot(exclude_today: bool = True) -> str | None:
    candidates = sorted(glob.glob(os.path.join(LOG_DIR, "parsed_*.json")))
    if not candidates:
        return None
    if not exclude_today:
        return candidates[-1]
    for p in reversed(candidates):
        if not p.endswith(f"parsed_{TODAY}.json"):
            return p
    return None

KEY_FIELDS = (
    "provider", "country", "country_iso", "country_code",
    "operator", "network", "mcc", "mnc", "number_type",
    "destination", "currency",
)

def _key_of(rec: Dict) -> Tuple:
    return tuple(rec.get(k) for k in KEY_FIELDS)

def _pick_new_price(rec: Dict) -> float | None:
    for k in ("new_price", "price", "current_rate"):
        v = rec.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None

def _pick_old_price(rec: Dict) -> float | None:
    for k in ("previous_rate", "old_price"):
        v = rec.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None

def diff_snapshots(prev_rows: List[Dict], today_rows: List[Dict]) -> Dict[str, List[Dict]]:
    prev_map = {_key_of(r): r for r in prev_rows}
    today_map = {_key_of(r): r for r in today_rows}

    changed, new, removed = [], [], []
    unchanged = 0

    for k, r_today in today_map.items():
        r_prev = prev_map.get(k)
        if r_prev is None:
            p_today = _pick_new_price(r_today) or _pick_old_price(r_today)
            new.append({"key": k, "today": r_today, "prev": None, "old": None, "new": p_today, "delta": None, "direction": "new"})
            continue
        p_prev = _pick_new_price(r_prev) or _pick_old_price(r_prev)
        p_today = _pick_new_price(r_today) or _pick_old_price(r_today)
        if p_prev is None and p_today is None:
            unchanged += 1
        elif p_prev is None and p_today is not None:
            changed.append({"key": k, "today": r_today, "prev": r_prev, "old": None, "new": p_today, "delta": None, "direction": "new-value"})
        elif p_prev is not None and p_today is None:
            changed.append({"key": k, "today": r_today, "prev": r_prev, "old": p_prev, "new": None, "delta": None, "direction": "missing-today"})
        else:
            if abs(p_today - p_prev) > 1e-12:
                delta = p_today - p_prev
                direction = "increase" if delta > 0 else "decrease"
                changed.append({"key": k, "today": r_today, "prev": r_prev, "old": p_prev, "new": p_today, "delta": delta, "direction": direction})
            else:
                unchanged += 1

    for k, r_prev in prev_map.items():
        if k not in today_map:
            p_prev = _pick_new_price(r_prev) or _pick_old_price(r_prev)
            removed.append({"key": k, "today": None, "prev": r_prev, "old": p_prev, "new": None, "delta": None, "direction": "removed"})

    return {"changed": changed, "new": new, "removed": removed, "unchanged_count": unchanged}


# ---------- Mailrender ----------
def _fmt(v):
    if v is None: return ""
    if isinstance(v, float): return f"{v:.6f}"
    return str(v)

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

    # Spara snapshots
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(today_rows, f, indent=2, ensure_ascii=False)
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(today_rows, f, indent=2, ensure_ascii=False)

    # Diff mot tidigare
    prev_path = find_previous_snapshot(exclude_today=True)
    prev_rows = load_snapshot(prev_path) if prev_path else []

    diff = diff_snapshots(prev_rows, today_rows)
    html = render_diff_html(diff)

    subject = f"SMS Price Summary {TODAY} – Changed:{len(diff['changed'])} New:{len(diff['new'])} Removed:{len(diff['removed'])}"
    send_email(subject=subject, html_body=html)
    print("\n📤 Daglig summering skickad.")


if __name__ == "__main__":
    main()
