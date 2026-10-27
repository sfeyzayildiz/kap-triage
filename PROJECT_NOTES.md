# Project Notes (Matriks Rules)
- Maximum 1 request per second (1 req/sec) to the API.
- Raw data must never be uploaded to GitHub.
- Matriks must be mentioned as the data source in the project presentation.
- API access is valid until the end of December.

## KAP Manual Discovery Notes (New Business Relationships)
- **Amount and Currency:** Explicitly stated in the text (e.g., 621,000 USD and its TRY equivalent).
- **Counterparty:** Sometimes explicitly named, but often anonymized due to trade secrets (e.g., "a domestic defense industry company").
- **Duration/Delivery Date:** Specific delivery dates or target deadlines are explicitly provided in the text (e.g., 30.11.2026).
- **Data Location:** Primary data points are located directly in the "Explanations" (Açıklamalar) text area. PDF attachments are not required to extract the core information.

## KAP Manual Discovery Example (FORTE Disclosure)
- **Is the amount stated? In which currency?** Yes. The amount is explicitly stated as 621,000 USD (with its approximate TRY equivalent of 30,779,679 TRY).
- **Is the counterparty explicitly named?** No, the company name is concealed due to trade secrets. It is anonymously referred to as "a domestic defense industry company" (yurt içinde yerleşik bir savunma sanayi şirketi).
- **Is there a duration or delivery date?** Yes. A clear deadline is specified in the text, stating the delivery target is by 30.11.2026.
- **Is the information in the disclosure text or in a PDF attachment?** All required information is located directly in the "Explanations" (Açıklamalar) text field. There are no PDF attachments, meaning PDF parsing is not required to extract the data.

## Baseline failure modes (15 manual samples, 12/15 correct)
- id 1: multiple amounts in text, regex picks the first
- id 7: amount written with 'milyon'
- id 14: amount written with 'milyar'
## Extraction Rules
- **counterparty_name**: proper names only (full or partial, e.g. 'Turkcell Grup şirketleri'). Descriptions like 'bir banka' → null.
## Dev set results (15 manual samples, gemma4:e4b)
| field | regex | LLM |
| amount | 12/15 | 15/15 |
| currency | 12/15 | 15/15 |
Known LLM issue: hallucinated related_party (id 14)
Note: prompt tuned on these samples, numbers optimistic
## Collector design notes

- **Archive range:** Matriks KAP archive starts January 2024, so a full pull covers roughly 3 years of data.
- **Pagination:** The endpoint returns at least 100 records in a single call (no hard upper limit observed at 100). Full company pulls will still be chunked monthly, so that any hidden limit is respected and a failed request only needs retrying for that month.
## Data quality: disclosures without a Matriks record

205 of 1,269 disclosures have no matching `new_business` record. URL formats are identical, and the gap is spread evenly over time, so this is neither a join error nor a lag.

The cause is the amount: 87% of matched disclosures mention an amount in the text, versus only 14% of unmatched ones. Matriks appears to create a record only when an amount is disclosed. Some companies (e.g. HTTBT, EFORC, DOAS) never appear in `new_business` because they usually omit it.

These ~180 disclosures are where LLM extraction adds the most value: counterparty, subject, duration and origin are in the text, but no structured source covers them.

### Lost currency symbol

The Turkish lira sign (₺) never appears in the collected texts: in 18 disclosures it shows up as a literal `?` right after the amount. Turkish letters survive, so the text was most likely converted to cp1254 upstream, which has no ₺. `llm_extract.py` falls back to reading the currency next to the extracted amount and maps that `?` to TRY.
## Daily collection

- Daily collector (`scripts/daily_collect.py`) re-fetches the last 3 days and sends an ntfy alert (OK / FAILED).
- Planned to run on the rented server, but the server ([server-ip]) cannot reach any Matriks address: TCP timeouts on 443 and 80, while the server firewall allows outbound traffic and the Mac connects fine. Asked Matriks whether the IP is restricted (27 Oct).
- Until then it runs on the Mac via launchd (`deploy/com.feyza.kap-daily.plist`), daily at 23:43; runs on wake if the Mac was asleep. Log: `data/daily.log`.
- The server clone and its read-only deploy key are ready if access is granted.