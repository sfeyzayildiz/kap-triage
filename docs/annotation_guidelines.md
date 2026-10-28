# Annotation Guidelines: Contract Amount
Version 1.2 (2026-10-28). Changes since 1.1: mixed-currency deals get a headline amount from the TL total written in the text (R6).

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
If orders are in different currencies, do not sum them: set `amount` and `currency` to null and `needs_review=true` (reason `multi_currency_items`). A partial sum in one currency would understate the deal.

### R4. Total vs company share
Use the company's share (the part that affects the company's revenue). Store the full contract value in `total_amount`.

### R5. Revisions
Use the current (revised) amount. Set `is_revision=true` and store the old amount in `previous_amount`.

### R6. Mixed currencies: headline amount
Some deals have parts in more than one currency: one contract paid partly in USD and partly in TL (R1, `mixed_currency`), or several orders in different currencies (R3, `multi_currency_items`).
- If the text writes a TL grand total for the whole deal ("toplam ... TL", "genel toplam ... TL"), store it in `amount_try_stated`. Copy only a figure the text writes; never calculate it.
- The headline amount is that TL total (`headline_amount`, `headline_currency=TRY`). This rule is applied in code, not by the model.
- If the text writes no TL total, the headline amount is `amount` (R1: the first part; R3: null) and the case stays `needs_review`.
- If the company's share of the total is not clear (consortium, joint venture), R4 applies: `needs_review=true`, reason `share_unclear`.
- The gold label for evaluation is the headline amount. For all other deals it equals `amount`.
- Annotator `needs_review` means the case cannot be decided. The system flag (`mixed_currency`) is different: it stays on so a human sees the deal. A mixed-currency case with a written TL total is decided: gold `needs_review=false`.
- Example: "2,000,000 USD and 30,000,000 TL, total 98,000,000 TL" → `amount=2000000`, `currency=USD`, `amount_try_stated=98000000`, headline 98,000,000 TRY.

## Known gaps
- Mixed-currency deals without a written TL total have no headline amount we can trust; they stay `needs_review`.
- Matriks is not consistent on mixed-currency deals: sometimes it reports the part in one currency, sometimes the TL total from the text. Disagreements on these cases are expected.
- When both item totals and a grand total are written, they are not yet checked against each other.
- Texts written as "X TL (Y EUR)" with no conversion wording do not say which currency is the contract currency. The gold label follows Matriks; this is a known ambiguity (e.g. 5702054, 6324169).

## Changelog
- 1.0 (2026-10-28): First version, based on Set A error analysis (10 disagreements with Matriks).
- 1.1 (2026-10-28): R3 states that multi-currency orders get a null amount and currency.
- 1.2 (2026-10-28): R6 added: the headline amount for mixed-currency deals is the TL total written in the text.