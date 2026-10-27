# Annotation Guidelines: Contract Amount

Version: 1.0 (2026-10-28)
Scope: "new business" disclosures (KAP). Defines the correct amount for gold labels and for the LLM extraction prompt.

## Principle
The LLM extracts facts stated in the text. It does not convert, calculate or interpret.
Business rules (headline amount, TRY conversion) are applied in code.

## Fields
| Field | Type | Description |
|---|---|---|
| `amount` | number | Headline amount (see rules below) |
| `currency` | string | Contract currency (ISO code: TRY, USD, EUR, ...) |
| `amount_try_stated` | number / null | TRY equivalent if the text states one |
| `vat_included` | bool / null | true only if no VAT-excluded amount is given |
| `n_items` | int | Number of orders/contracts in the disclosure |
| `total_amount` | number / null | Total contract value if different from the company's share |
| `is_revision` | bool | Disclosure revises an earlier contract amount |
| `previous_amount` | number / null | Amount before revision |
| `needs_review` | bool | Annotator or model could not decide |
| `review_note` | string / null | Short reason when `needs_review` is true |

## Rules

### R1. Multiple currencies
Use the contract currency. A figure written as an equivalent ("... TL karşılığı", "... tutarında") is a conversion, not the contract amount; store it in `amount_try_stated`.
- "350,000 USD (12.2M TL equivalent)" → `amount=350000`, `currency=USD`, `amount_try_stated=12200000`
- If the contract currency cannot be determined, do not guess: set `needs_review=true`.
- TRY conversion for comparison is done in code with the CBRT (TCMB) rate on the publication date.

### R2. VAT
Use the VAT-excluded amount. If only a VAT-included amount is given, use it and set `vat_included=true`.

### R3. Multiple orders
Use the sum of all orders in the disclosure, in the same currency. Set `n_items` to the number of orders.
If orders are in different currencies, set `needs_review=true`.

### R4. Total vs company share
Use the company's share (the part that affects the company's revenue). Store the full contract value in `total_amount`.

### R5. Revisions
Use the current (revised) amount. Set `is_revision=true` and store the old amount in `previous_amount`.
## Known gaps
- Mixed-currency contracts (e.g. part in USD, part in TRY) are not covered. Mark as `needs_review`. Revisit if more cases appear.

## Changelog
- 1.0 (2026-10-28): First version, based on Set A error analysis (10 disagreements with Matriks).