import os
from llm.extractor import extract_sms_prices_llm

def test_mock_llm_extract(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    text = """
    Country: Kuwait
    Operator: zain
    MCC 419, MNC 02
    Old Price 0.0300 EUR
    New Price 0.0305 EUR
    Effective Date 2025-09-08
    Change: Increase
    """
    rows = extract_sms_prices_llm(text, provider_hint="Demo")
    assert rows and rows[0]["country"] == "Kuwait"
    assert rows[0]["mcc"] == "419"
    assert rows[0]["mnc"] == "02"
    assert rows[0]["old_price"] == 0.03
    assert rows[0]["new_price"] == 0.0305
    assert rows[0]["currency"] == "EUR"
