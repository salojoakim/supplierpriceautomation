import os
from email.message import EmailMessage
from utils.email_reader import iter_eml_messages
from utils.mailer import send_email

def test_dry_run_html(tmp_path, monkeypatch):
    # skapa en enkel eml i tempkatalog
    msg = EmailMessage()
    msg["From"] = "a@x.se"; msg["To"] = "b@x.se"; msg["Subject"] = "Price"
    msg.set_content("Country: Testland\nRate 0.12 EUR\n")
    eml = tmp_path / "mail.eml"
    with open(eml, "wb") as f:
        f.write(bytes(msg))

    # rendera ett litet html och spara i DRY_RUN
    monkeypatch.setenv("DRY_RUN", "true")
    html = "<html><body><h1>Hej</h1></body></html>"
    send_email("Test", html)
    # borde skapa fil i logs/outbox
    assert os.path.isdir("logs/outbox")
