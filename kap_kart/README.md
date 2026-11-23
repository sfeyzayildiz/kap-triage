# kap-kart

Paste the text of a public KAP "Yeni İş İlişkisi" (new business relationship) disclosure, get a card: amount, currency, revision, counterparty, duration, the source sentence with the amount marked, and a **KONTROL ET** (check this) warning with reasons when the text is ambiguous.

It is the extraction step of a larger, measured analyst system, copied byte for byte (one file without its self-test, see Files). Everything runs on your own computer with a local model; the text is never sent anywhere and never written to disk.

## Hızlı başlangıç (Türkçe)
1. [Ollama](https://ollama.com) kurun ve açın. Modeli bir kez indirin (yaklaşık 9,5 GB): `ollama pull gemma4:e4b`
2. Bu klasörde: `./run.sh`
3. Tarayıcıda `http://127.0.0.1:8770` açılır. kap.org.tr'den bir "Yeni İş İlişkisi" bildiriminin metnini kopyalayıp yapıştırın ya da hazır örneklerden birini seçin. Bir kart yaklaşık 30-60 saniye sürer.

Komut satırı: `python kap_kart.py metin.txt` ya da `pbpaste | python kap_kart.py`.

## What the card does
1. **Extraction:** prompt v3 with `gemma4:e4b` (thinking on, temperature 0, context 8192) returns structured fields (pydantic schema).
2. **Code checks** flag, never fix: currency unclear (a TL amount with a foreign amount in brackets), amount may be a projection, amount may be a cumulative total.
3. **Second reading:** the text is extracted twice; a different amount or currency adds a flag.
4. **Source sentence:** code finds the sentence that contains the amount (an amount not in the text is flagged); a second model call judges whether that sentence is a fact or an instruction to the model (prompt injection).

Fields and flags come from the LLM and from code; business rules live in code, and the code only flags contradictions.

## Measured reliability (in the source project, not re-measured here)
- Held-out test set of 100 disclosures: **1 silent error** (wrong value without a warning; 95% upper bound 4.7%), 11 flagged (with all checks of the live system, about 20-22% of new texts were flagged). The strongest regex in the source project, without an LLM: 25 silent errors on the same set.
- Prompt injection: with no defence, one appended sentence changed the amount silently in 14 of 20 texts. The adopted defence (vendor cross-check + the source-sentence judge) took silent errors from 9 to 0 on 18 sealed attacks.
- Run to run, 3 of 100 texts changed amount or currency, which is why the card reads every text twice.

## Limits (read before trusting a card)
- **The vendor cross-check is not here.** The measured numbers above were taken with it. The injection defence here is the source-sentence layer alone. In the source project that layer alone also stopped 18 of 18 sealed attacks (mostly by noticing that the injected amount is not in the text), but only on texts that also had a vendor record; texts without one were not tested.
- **No importance score**, revenue ratio, FX conversion, sector or price: those need licensed market data.
- Only "Yeni İş İlişkisi" disclosures in Turkish were tested. Other disclosure types will give cards that look right and may not be.
- A card with no warning is not a guarantee. Check the source sentence and the KAP page.

## Trap examples
`examples/` holds four made-up texts (not real disclosures): a clean one, an unclear currency, a revision, and a hidden instruction. `python kap_kart.py --examples` runs each three times and prints how many behaved as expected and how long each card took. The expected behaviour was fixed before the first run.

## No data included
This folder contains code, one prompt, four made-up examples and documentation. It contains no disclosure texts, no market data, no labels and no credentials. Before release it is scanned for files outside an allowlist, for forbidden strings and for 12-word overlaps with the source project's disclosure corpus; all three counts must be 0.

## Files
- `kap_kart.py`: card, command line, paste page, trap examples, self-test (`--self-test`, no model needed).
- `frozen/`, `prompts/`: byte-copies of the measured extraction code and prompt (`amount_checks.py` without its self-test, which held a real disclosure fragment); `MANIFEST.sha256` holds their hashes and the self-test checks them.
- `run.sh`: launcher. `requirements.txt`: pinned versions. `LICENSE`: MIT.

Author: Feyza Yıldız, 2026.
