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
