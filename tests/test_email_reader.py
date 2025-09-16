
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
