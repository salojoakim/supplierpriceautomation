# utils/price_analyzer.py
"""
Price snapshot & diff utilities.

- load_previous_prices(path) -> list[dict]
- save_current_prices(rows, path) -> writes JSON snapshot (+ updates latest.json)
- compare_prices(current_rows, prev_rows) -> dict with Changed/New/Removed

Vi försöker vara toleranta mot olika fältnamn från leverantörer.
Unik rad-id sätts med en nyckel byggd på (country, network/operator, mcc, mnc, currency).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


# -------- Helpers -------------------------------------------------------------

_PRICE_KEYS = ("rate", "price", "new_rate", "new_price")
_CURRENCY_KEYS = ("currency", "cur")
_NETWORK_KEYS = ("network", "operator", "mno", "carrier")
_COUNTRY_KEYS = ("country", "country_name", "countrynam")
_MCC_KEYS = ("mcc",)
_MNC_KEYS = ("mnc",)


def _first_value(d: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    """Hitta första förekomsten av något av keys (case-insensitive)."""
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k in lower:
            return lower[k]
    # prova trimma space i nycklar
    for k, v in lower.items():
        if k.replace(" ", "") in keys:
            return v
    return None


def _as_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(str(x).strip().replace(",", "."))
    except Exception:
        return None


def _norm_str(x: Any) -> str:
    return str(x).strip().lower() if x is not None else ""


def _row_key(row: Dict[str, Any]) -> str:
    """
    Bygg en robust nyckel för att identifiera en prisrad.
    Anpassa vid behov om ni har andra fält som bör ingå.
    """
    country = _norm_str(_first_value(row, _COUNTRY_KEYS))
    network = _norm_str(_first_value(row, _NETWORK_KEYS))
    mcc = _norm_str(_first_value(row, _MCC_KEYS))
    mnc = _norm_str(_first_value(row, _MNC_KEYS))
    currency = _norm_str(_first_value(row, _CURRENCY_KEYS))

    # fallback om nätverksnamn saknas men operator finns
    if not network and "operator" in {k.lower() for k in row.keys()}:
        network = _norm_str(row.get("operator"))

    # bygg nyckel – ordning viktig men ganska tolerant
    return "|".join([country, network, mcc, mnc, currency])


def _price_of(row: Dict[str, Any]) -> float | None:
    return _as_float(_first_value(row, _PRICE_KEYS))


def _to_map(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows or []:
        out[_row_key(r)] = r
    return out


# -------- Public API ----------------------------------------------------------

def load_previous_prices(file_path: str | Path) -> List[Dict[str, Any]]:
    """
    Läs in föregående snapshot (JSON). Returnerar tom lista om fil saknas.
    """
    p = Path(file_path)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # data kan vara {"date": "...", "rows": [...] } eller bara [...]
        if isinstance(data, dict) and "rows" in data:
            return list(data["rows"])
        elif isinstance(data, list):
            return data
        else:
            return []
    except Exception:
        # hellre tom lista än att krascha i produktion
        return []


def save_current_prices(current_prices: List[Dict[str, Any]], file_path: str | Path) -> None:
    """
    Spara dagens snapshot som JSON. Skapar kataloger vid behov.
    Uppdaterar också en syskonfil 'latest.json'.
    """
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rows": list(current_prices)}
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # uppdatera latest.json i samma katalog
    latest = p.parent / "latest.json"
    with latest.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def compare_prices(
    current_prices: List[Dict[str, Any]],
    previous_prices: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Jämför två uppsättningar prisrader och returnerar diff:
      {
        "changed": [{"before": {...}, "after": {...}, "delta": +0.0123}, ...],
        "new":     [{...}, ...],
        "removed": [{...}, ...],
        "summary": {"changed": N, "new": M, "removed": K}
      }
    """
    cur_map = _to_map(current_prices)
    prev_map = _to_map(previous_prices)

    changed: List[Dict[str, Any]] = []
    new: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []

    # new + changed
    for k, cur in cur_map.items():
        prev = prev_map.get(k)
        if prev is None:
            new.append(cur)
            continue

        cur_price = _price_of(cur)
        prev_price = _price_of(prev)
        # Om någon av priserna saknas – betrakta som changed om raderna inte är identiska
        if cur_price is None or prev_price is None:
            if json.dumps(cur, sort_keys=True) != json.dumps(prev, sort_keys=True):
                changed.append({"before": prev, "after": cur, "delta": None})
        else:
            if abs(cur_price - prev_price) > 1e-9:
                changed.append({"before": prev, "after": cur, "delta": cur_price - prev_price})

    # removed
    for k, prev in prev_map.items():
        if k not in cur_map:
            removed.append(prev)

    return {
        "changed": changed,
        "new": new,
        "removed": removed,
        "summary": {
            "changed": len(changed),
            "new": len(new),
            "removed": len(removed),
        },
    }
