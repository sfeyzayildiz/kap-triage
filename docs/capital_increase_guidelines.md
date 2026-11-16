# Annotation Guidelines: Capital Increase (pilot)
Version 0.1 (2026-11-16). Written before any capital-increase text was pulled or seen. The 8 dev texts are also the shakedown of this guideline (see "Versions").

Scope: KAP disclosures that Matriks tags `CapitalIncrease`. Defines the gold label for the pilot in `docs/capital_increase_rule.md`.

## Principle
Label what this disclosure writes. Do not calculate, convert or complete from memory or from another disclosure. A figure in a form cell counts as written.

You see only the text of the disclosure: no Matriks record, no model output, no reader output. If you already know the event from the news, label the text anyway.

## Fields
| Field | Answer | Description |
|---|---|---|
| `subject` | `self` / `other` / `none` | Whose capital is increased (C1) |
| `rights` | y / n | Bedelli with pre-emptive rights, rüçhan hakkı kullandırılarak (C3) |
| `rights_rate_pct` | number / `-` | Rate as written, in percent (C4) |
| `rights_price_try` | number / `-` | Exercise price as written (C6) |
| `bonus` | y / n | Bedelsiz (C3) |
| `bonus_internal_rate_pct` | number / `-` | Bonus rate from internal resources (C5) |
| `bonus_dividend_rate_pct` | number / `-` | Bonus rate from profit, kâr payından (C5) |
| `restricted` | y / n | Rights restricted, rüçhan hakkı kısıtlanarak: tahsisli or public sale (C7) |
| `restricted_amount_try` | number / `-` | Nominal amount as written (C7) |
| `stage` | one of seven | Latest step this disclosure reports (C9) |
| `needs_review` | y / n | You could not decide (C13) |
| `note` | short text | Tags from the rules below, or a few words; never the disclosure text |

`-` means "not written in this text". The tool skips the number questions of a component answered `n`.

## Rules

### C1. Subject
- `self`: the disclosing company increases its own capital.
- `other`: the text is about another company's capital (a subsidiary, an affiliate, a company it invests in). All components `n`, stage `other`.
- `none`: no capital increase is described (only a ceiling change, only a decrease, an unrelated notice under this tag). All components `n`, stage `other`.

### C2. The registered ceiling is not capital
"Kayıtlı sermaye tavanı" never goes into any field, however close it stands to the other numbers.

### C3. Components separately
An increase can have up to three components at once: rights (bedelli, rüçhanlı), bonus (bedelsiz), restricted (tahsisli or public sale). Answer each on its own. Never label the total increase or the new capital as a component.

### C4. Rates
- Write a rate only if the text writes a percentage for that component. Never derive it from amounts ("100'den 300'e" is not a written rate).
- A ratio in words ("her 1 paya 2 pay") is not a percentage: rate `-`, note `ratio_in_words`.
- Write the number as a percentage of current capital: "%200" → `200`, "% 33,33333" → `33.33333`, "% 1.900" → `1900`. Keep the decimals the text gives.
- Share groups (A, B, C): the same rate repeated per group is written once. Different rates per group → `needs_review`, note `group_rates_differ`.

### C5. Bonus sources
- The form separates "iç kaynaklardan" and "kâr payından". Put each rate in its own field; do not add them.
- Source not stated ("%100 bedelsiz"): use the internal field, note `source_unstated`.

### C6. Rights price
- The exercise price for the new shares as written: "1 TL nominal değerli pay için 1 TL" → `1`; "beheri 5,00 TL" → `5`.
- If the price refers to a nominal value other than 1 TL (for example 1 Kr shares), write the price as written and note `nominal_not_1`.
- "Nominal değer üzerinden" with no number → `-`, note `at_nominal`. Price to be set later → `-`.
- This is the price of the rights component only. A tahsisli price is not labeled.

### C7. Restricted issues
- `restricted=y` when existing holders' rights are restricted in whole or in part: a tahsisli sale to named or unnamed buyers, or a public sale of the new shares.
- Amount: the nominal amount as written. An upper limit ("… TL'ye kadar", "azami") is written as that limit, note `up_to`. A total sale value (nominal × price) is not the nominal amount; if only that is written → `-`, note `sale_value_only`.
- Note `public_offering` when the shares are sold to the public instead of to chosen buyers.

### C8. Updates and repeated history
Most disclosures of this type are updates that repeat the earlier steps. Label the increase as it stands in this disclosure: its current terms and the latest step. Earlier steps quoted in the text do not make a second increase.
If the terms changed (rate, price, amount revised), label the current ones, note `revised`.

### C9. Stage
The latest step the text reports as having happened.

| Stage | Meaning |
|---|---|
| `decision` | The board or the general assembly decided; no application to the SPK reported yet |
| `application` | Application to the SPK made (also a renewed or amended application) |
| `approval` | The SPK approved (prospectus or issue document) |
| `exercise` | Exercise dates announced, exercise period running, or unused shares being sold |
| `completed` | The increase is completed: results announced, new capital registered |
| `cancelled` | Withdrawn, rejected or cancelled (C10) |
| `other` | None of these: for example a report on how the proceeds were used |

A planned date is not a step: "rüçhan hakları … tarihinde kullandırılacaktır" is `exercise` (dates announced); "SPK'ya başvurulacaktır" stays `decision`.

### C10. Cancelled increases
Stage `cancelled`. Components and numbers are labeled as the text writes the cancelled plan; if the text gives no terms, components `n`.

### C11. Decrease together with increase
Simultaneous decrease and increase (eş anlı sermaye azaltımı ve artırımı): `needs_review=y`, note `simultaneous_decrease`. Label the increase components as written if you can.

### C12. Planned and realized
At `completed`, if the text gives both the planned and the realized figures and they differ, label the planned terms (rates, price), note `partial_completion`.

### C13. `needs_review`
Set it when two readings stay possible after applying the rules. Do not set it because the text is long or dull. Write the reason in `note`.

## Known gaps (v0.1)
- Capital before / after, amounts of the rights and bonus components and the milestone dates are extracted but not labeled, so the pilot does not score them.
- The tahsisli price and buyer are not labeled.
- The realized outcome of a completed increase is not labeled (C12).
- One labeler, no second annotator.

## Versions
- 0.1 (2026-11-16): first version, written blind from the structure of the KAP form and the Matriks docs.
- Shakedown: Feyza labels the 8 dev texts first and reports where a rule did not fit, as rule numbers and tags only, never as text. Changes go into v0.2 before the first held-out text is labeled; dev labels are redone under v0.2 if a changed rule touches them. From the first held-out label on, the guideline is frozen for this pilot.
