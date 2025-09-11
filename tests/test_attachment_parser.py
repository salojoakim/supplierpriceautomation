import pandas as pd
from io import BytesIO
from utils.attachment_parser import parse_attachments

def _excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        df.to_excel(xw, index=False)
    return bio.getvalue()

def test_parse_excel_basic():
    df = pd.DataFrame({
        "Country": ["Kuwait"],
        "MCC": [419],
        "MNC": ["02"],
        "Rate(EUR)": [0.0305],
        "Currency": ["EUR"]
    })
    content = _excel_bytes(df)
    attachments = [{
        "filename": "prices.xlsx",
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "data": content
    }]
    out = parse_attachments(attachments, provider_hint="TestProv")
    assert out["rows"]
    r = out["rows"][0]
    assert r["country"] == "Kuwait"
    assert r["mcc"] == "419"
    assert r["mnc"] == "02"
    assert r["price"] == 0.0305
    assert r["currency"] == "EUR"
