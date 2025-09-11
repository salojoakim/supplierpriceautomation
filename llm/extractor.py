import os
import re
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Produktions-LLM (Gemini) – används endast om MOCK_LLM=false
import google.generativeai as genai

from .prompt_templates import PRICE_EXTRACTION_PROMPT

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

_MODEL_NAME = "gemini-1.5-flash"
_MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes")


def _first_json(text: str) -> Optional[str]:
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.S)
    if m:
        return m.group(1)
    m2 = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
    return m2.group(1) if m2 else None


def _to_float(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x)
    s = s.replace("€", "").replace("$", "").replace("£", "")
    s = s.replace("\u00a0", " ").strip()
    s = s.replace(",", ".")
    s = re.sub(r"[A-Za-z]", "", s)
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", ".", "-"):
        return None
    try:
        return float(s)
    except Exception:
        return None


_NUMERIC_KEYS = {"previous_rate", "old_price", "current_rate", "new_price", "price", "count", "cost"}

def _normalize_record(rec: Dict) -> Dict:
    out = dict(rec)
    # numeriska
    for k in list(out.keys()):
        if k in _NUMERIC_KEYS:
            out[k] = _to_float(out.get(k))
    # variation normaliserad
    var = out.get("variation")
    if isinstance(var, str):
        v = var.strip().lower()
        mapping = {
            "up": "increase", "increase": "increase", "inc": "increase",
            "down": "decrease", "decrease": "decrease", "dec": "decrease",
            "unchanged": "unchanged", "no change": "unchanged", "nochange": "unchanged",
            "new": "new"
        }
        out["variation"] = mapping.get(v, v)
    # tomma string -> None
    for k, v in list(out.items()):
        if isinstance(v, str) and v.strip() == "":
            out[k] = None
    return out


# ---------------- MOCK-LLM (regelbaserad) ----------------
_COUNTRY_RE = re.compile(r"\bcountry(?:\s*iso)?\s*[:=]\s*([A-Za-z ()/&'-]+)", re.I)
_OPERATOR_RE = re.compile(r"\b(operator|network)\s*[:=]\s*([A-Za-z0-9 ()/&'._-]+)", re.I)
_MCC_RE = re.compile(r"\bmcc\D{0,5}(\d{2,4})\b", re.I)
_MNC_RE = re.compile(r"\bmnc\D{0,5}(\d{1,4})\b", re.I)
_CUR_RE = re.compile(r"\b(EUR|USD|SEK|GBP)\b", re.I)
_OLD_RE = re.compile(r"\b(old price|previous rate|old rate|current rate)\b\D{0,10}([0-9][0-9.,]*)", re.I)
_NEW_RE = re.compile(r"\b(new price|rate)\b\D{0,10}([0-9][0-9.,]*)", re.I)
_CHG_RE = re.compile(r"\b(increase|decrease|unchanged|up|down|new)\b", re.I)
_DATE_RE = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\b")


def _rule_based_extract(email_text: str, provider_hint: Optional[str]) -> List[Dict]:
    """
    Enkel, robust parser för test/simulering: letar utvalda fält i text.
    Skapar 1 rad per stycke/rad där minst pris hittas.
    """
    rows: List[Dict] = []

    # dela upp i stycken för “en rad per block”
    blocks = [b.strip() for b in re.split(r"\n{2,}", email_text) if b.strip()]

    for block in blocks:
        # hitta prisindikatorer i blocket
        old_match = _OLD_RE.search(block)
        new_match = _NEW_RE.search(block)

        if not (old_match or new_match):
            # försök fall: ensamma "Rate(EUR) 0.123" eller "Price 0.12"
            solo = re.search(r"\b(rate|price)\b\D{0,10}([0-9][0-9.,]*)", block, re.I)
            if not solo:
                continue

        country = None
        country_m = _COUNTRY_RE.search(block)
        if country_m:
            country = country_m.group(1).strip()

        operator = None
        op_m = _OPERATOR_RE.search(block)
        if op_m:
            operator = op_m.group(2).strip()

        mcc = None
        mnc = None
        mcc_m = _MCC_RE.search(block)
        if mcc_m:
            mcc = mcc_m.group(1)
        mnc_m = _MNC_RE.search(block)
        if mnc_m:
            mnc = mnc_m.group(1)

        currency = None
        cur_m = _CUR_RE.search(block)
        if cur_m:
            currency = cur_m.group(1).upper()

        variation = None
        chg_m = _CHG_RE.search(block)
        if chg_m:
            variation = chg_m.group(1)

        eff = None
        d_m = _DATE_RE.search(block)
        if d_m:
            eff = d_m.group(1).replace("/", "-")

        # priser
        old_val = _to_float(old_match.group(2)) if old_match else None
        new_val = _to_float(new_match.group(2)) if new_match else None
        if new_val is None:
            solo = re.search(r"\b(rate|price)\b\D{0,10}([0-9][0-9.,]*)", block, re.I)
            if solo:
                new_val = _to_float(solo.group(2))

        row = {
            "provider": (provider_hint or None),
            "country": country,
            "country_iso": None,
            "country_code": None,
            "operator": operator,
            "network": None,
            "mcc": mcc,
            "mnc": mnc,
            "imsi": None,
            "nnc": None,
            "number_type": None,
            "destination": None,
            "previous_rate": old_val,     # spegla in i old_price också
            "old_price": old_val,
            "current_rate": None,
            "new_price": new_val,
            "price": new_val if old_val is None else None,
            "currency": currency,
            "variation": variation,
            "effective_from": eff,
            "count": None,
            "cost": None,
            "product_category": None,
            "notes": None
        }
        rows.append(_normalize_record(row))

    return rows


# ---------------- Publika funktionen ----------------
def extract_sms_prices_llm(email_text: str, provider_hint: Optional[str] = None) -> List[Dict]:
    """
    MOCK_LLM=true  -> använd snabb regelbaserad parser (ingen API-kostnad)
    MOCK_LLM=false -> använd Gemini via google-generativeai
    """
    if not email_text or not email_text.strip():
        return []

    if _MOCK_LLM:
        return _rule_based_extract(email_text, provider_hint)

    # produktionsläge: Gemini
    prompt = PRICE_EXTRACTION_PROMPT.format(
        email=email_text.strip(),
        provider_hint=(provider_hint or "")
    )
    model = genai.GenerativeModel(_MODEL_NAME)

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        json_str = _first_json(raw) or raw
        data = json.loads(json_str)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        return [_normalize_record(r) for r in data if isinstance(r, dict)]
    except Exception as e:
        print(f"❌ LLM/parsningsfel: {e}")
        return []
