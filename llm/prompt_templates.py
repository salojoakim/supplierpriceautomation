PRICE_EXTRACTION_PROMPT = """
Du är en assistent som analyserar prisuppdateringar från SMS-leverantörer
och extraherar *strukturerad* data från e-post (tabeller eller löptext).

VIKTIGT:
- Returnera ENBART en giltig JSON-array (inga rubriker/kommentarer/kodblock).
- En rad i tabellen/löptexten = ett objekt i arrayen.
- Om ingen prisinformation hittas, returnera [].

SCHEMA (alla fält är valfria; saknas värde -> null):
{{
  "provider": string|null,
  "country": string|null,
  "country_iso": string|null,
  "country_code": string|null,
  "operator": string|null,
  "network": string|null,
  "mcc": string|null,
  "mnc": string|null,
  "imsi": string|null,
  "nnc": string|null,
  "number_type": string|null,
  "destination": string|null,
  "previous_rate": number|null,
  "old_price": number|null,
  "current_rate": number|null,
  "new_price": number|null,
  "price": number|null,
  "currency": string|null,
  "variation": string|null,        // normalize: increase/decrease/unchanged/new
  "effective_from": string|null,   // ISO: YYYY-MM-DD eller YYYY-MM-DDThh:mm:ssZ
  "count": number|null,
  "cost": number|null,
  "product_category": string|null,
  "notes": string|null
}}

REGLER:
- Tolka tal robust: "0.17838 €", "EUR 0,17838", "Rate(EUR) 0.17838" ⇒ price=0.17838, currency="EUR".
- "Previous/Old/Current/New Rate" mappas till previous_rate/old_price/current_rate/new_price respektive.
- "Valid/Eff. From/Effective Date/Valid (UTC)" ⇒ effective_from (ISO).
- "Change/Variation" normaliseras till: increase/decrease/unchanged/new.
- Kolumner som "MCC/MNC/IMSI/NNC/Number Type/Count/Cost(EUR)/Product category" stöds.
- Om bara en kolumn "Rate" finns: sätt price, och försök härleda currency från rubriken eller radens text.

HINT OM LEVERANTÖR (kan hjälpa dig att sätta 'provider'):
{provider_hint}

E-POSTINNEHÅLL:
\"\"\" 
{email}
\"\"\" 

RETURNERA ENBART EN JSON-ARRAY ENLIGT SCHEMAT.
"""
