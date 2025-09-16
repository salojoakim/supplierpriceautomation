"""
Read .eml emails and return a clean, uniform structure for the pipeline:
- metadata (subject, from, date)
- plain body text (HTML is stripped to text)
- raw attachments (filename, MIME type, bytes)

Why: downstream code (LLM + attachment parser) should not worry about email internals.
This module does NOT parse attachment content — it only exposes it for others to handle.
"""


from email.message import EmailMessage
from utils.email_reader import load_eml_body

def test_load_eml_body_plain(tmp_path):
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Subject"] = "Test"
    msg.set_content("Hello plain world")
    p = tmp_path / "mail.eml"
    with open(p, "wb") as f:
        f.write(bytes(msg))
    body = load_eml_body(str(p))
    assert "Hello plain world" in body
