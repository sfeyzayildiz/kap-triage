# Annotation Guidelines: Finansal Duran Varlık Edinimi / Satışı (pilot)
Version 0.1 (2026-11-19), written before any text of this type was pulled or seen. Defines the gold label for `docs/fdv_pilot_rule.md`.

## Principle
Label what this disclosure writes. Do not calculate, convert or complete from memory or another disclosure. A figure in a form cell counts as written. You see only the text: no reader output. If you know the deal from the news, label the text anyway.

## Fields
| Field | Türkçe | Answer | Description |
|---|---|---|---|
| `direction` | yön | `acquisition` / `sale` / `none` | F1 |
| `target` | edinilen / satılan şirket | name as written / `-` | F2 (report only) |
| `amount` | işlem bedeli | number / `-` | F3 |
| `currency` | para birimi | `TRY` / `USD` / `EUR` / other ISO code / `-` | F4 |
| `stake_pct` | bu işlemle alınan/satılan pay (%) | number / `-` | F5 |
| `stake_after_pct` | işlem sonrası pay (%) | number / `-` | F6 (report only) |
| `related_party` | ilişkili taraf | y / n / `-` | F7 |
| `needs_review` | incelenmeli | y / n | F10 |
| `note` | not | tags | From the tag list; never the disclosure text |

`-` means "not written in this text".

## Rules

### F1. Direction
- `acquisition`: the disclosing company acquires shares of another company: a purchase, founding a new company, or joining another company's capital increase.
- `sale`: it sells or transfers shares of another company it holds.
- `none`: no acquisition or sale is described (only an intention, negotiations without a decision, an unrelated notice). All other fields `-`.
- A cancelled transaction: the direction of the cancelled plan, note `cancelled`.

### F2. Target
The company whose shares change hands, as written (short form is fine). Report only.

### F3. Amount
- The transaction value for the shares in this transaction, as written: "toplam tutar", "alış bedeli", "satış bedeli", "pay devir bedeli".
- Founding a company or joining a capital increase: the capital the disclosing company commits or pays, as written, note `at_nominal` if it is the nominal value.
- Not the amount: the target's capital, the nominal value of shares bought for a different price, the company's total assets, a valuation report figure that is not the price.
- Upper limit ("… TL'ye kadar", "azami") → the limit, note `up_to`. Price to be set later → `-`, note `price_later`. Payment in shares or other non-cash form with no value written → `-`, note `non_cash`.
- Installments or several payments: the total if the text writes it; otherwise `-`, note `no_total`.
- Write the number fully: "15 milyon" → `15000000`, "1.250.000,50" → `1250000.5`.

### F4. Currency
The currency of the amount as written, ISO code (TL → `TRY`). An amount given in a foreign currency with a TL equivalent: label the foreign currency and its amount, note `try_equivalent`. Two currencies and you cannot tell which is the price → `needs_review`, note `mixed_currency`. Amount `-` → currency `-`.

### F5. Stake in this transaction
- The share of the target's capital acquired or sold in this transaction, in percent: "%25" → `25`, "% 33,33" → `33.33`.
- Not the stake after the transaction. If only the stake after is written and the stake before is written as 0 or the target is newly founded, the stake in this transaction equals it. If the stake before is not written, `-`, note `after_only`.
- Never derive it from share counts or amounts.

### F6. Stake after
The disclosing company's share of the target's capital after the transaction, as written. Report only.

### F7. Related party
`y` if the text says the counterparty is a related party ("ilişkili taraf") or the form answers "Evet" to the related-party question; `n` if it says no; `-` if not stated. Do not infer it from names.

### F8. Updates and revisions
Label the transaction as it stands in this disclosure. Changed terms: the current ones, note `revised`. A later step of an earlier deal (closing, registration) without new terms: label the terms the text repeats; if it repeats none, `-`.

### F9. Several transactions in one disclosure
`needs_review=y`, note `multiple_targets`; label the first transaction the text describes.

### F10. `needs_review`
Set it when two readings stay possible after the rules. Tags that always set it: `mixed_currency`, `multiple_targets`, `two_readings_possible`. Every other tag leaves it `n`.

## Tag list (use only these in `note`)
| Tag | Rule | Meaning |
|---|---|---|
| `cancelled` | F1 | The transaction was cancelled |
| `at_nominal` | F3 | Amount is the nominal capital committed |
| `up_to` | F3 | Upper limit written as the amount |
| `price_later` | F3 | Price to be set later |
| `non_cash` | F3 | Non-cash payment, no value written |
| `no_total` | F3 | Several payments, no total written |
| `try_equivalent` | F4 | Foreign amount labeled, TL equivalent also written |
| `mixed_currency` | F4 | Price currency unclear (review) |
| `after_only` | F5 | Only the stake after is written |
| `revised` | F8 | Terms changed; current ones labeled |
| `multiple_targets` | F9 | Several transactions (review) |
| `two_readings_possible` | F10 | Two readings remain (review) |

## Versions
- 0.1 (2026-11-19): written blind from the structure of the KAP form and the capital-increase pilot's lessons. Shakedown on the 8 dev texts (Feyza reports rule numbers and tags only, never text); changes go into v0.2 before the first held-out label, then frozen.
