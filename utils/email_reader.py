"""
Read .eml emails and return a clean, uniform structure for the pipeline:
- metadata (subject, from, date)
- plain body text (HTML is stripped to text)
- raw attachments (filename, MIME type, bytes)

Why: downstream code (LLM + attachment parser) should not worry about email internals.
This module does NOT parse attachment content — it only exposes it for others to handle.
"""


import os
from email import policy
from email.parser import BytesParser
from typing import Iterator, Dict, Any


def _extract_body(msg) -> str:
    # text/plain i första hand (ej bilagor)
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cd = (part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in cd:
                try:
                    return part.get_content()
                except Exception:
                    pass
        # fallback: ta HTML-innehåll om bara det finns
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_content()
                except Exception:
                    pass
        return ""
    else:
        try:
            return msg.get_content()
        except Exception:
            return ""


def _extract_attachments(msg):
    """
    Returnera lista av bilagor: dicts med keys:
      filename, content_type, data(bytes)
    """
    files = []
    if not msg.is_multipart():
        return files

    for part in msg.walk():
        cd = (part.get("Content-Disposition") or "").lower()
        if "attachment" in cd:
            fname = part.get_filename() or "attachment"
            ctype = part.get_content_type()
            data = part.get_payload(decode=True)  # bytes
            if data:
                files.append({
                    "filename": fname,
                    "content_type": ctype,
                    "data": data,
                })
    return files


def iter_eml_messages(root_dir: str) -> Iterator[Dict[str, Any]]:
    """
    Itererar över alla .eml-filer i en katalog och yieldar dict:
      { filename, body:str, attachments:list[ {filename, content_type, data} ] }
    """
    if not os.path.isdir(root_dir):
        return

    for name in sorted(os.listdir(root_dir)):
        if not name.lower().endswith(".eml"):
            continue
        path = os.path.join(root_dir, name)
        try:
            with open(path, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)
            yield {
                "filename": name,
                "body": _extract_body(msg),
                "attachments": _extract_attachments(msg),
            }
        except Exception as e:
            print(f"⚠️ Hoppar över {name}: {e}")
