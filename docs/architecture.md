# Architecture

Morning triage for KAP "Yeni İş İlişkisi" disclosures. Everything runs on one Mac: models are local (Ollama, sentence-transformers), and no data leaves the machine.

Design principle: **the LLM extracts facts, code applies business rules.** Code flags contradictions (`needs_review`) and never fixes them. Every number and KAP link shown to the analyst comes from code, not from model text.

## 1. Daily flow: from Matriks to the morning list

```mermaid
flowchart TD
    classDef store fill:#1f6feb,stroke:#1f6feb,color:#ffffff
    classDef llm fill:#8250df,stroke:#8250df,color:#ffffff
    classDef code fill:#2d333b,stroke:#768390,color:#ffffff
    classDef out fill:#1a7f37,stroke:#1a7f37,color:#ffffff

    SRC["Matriks (licensed)<br/>new-business-api, news, daily bars"]:::code
    COL["daily_collect.py + collector.py<br/>launchd 23:43, 1 req/s, one pull per day<br/>ntfy alert OK / FAILED"]:::code
    DB[("DuckDB<br/>disclosures, new_business, daily_bars")]:::store

    LLM["1 Extraction (LLM)<br/>gemma4:e4b, prompt v3"]:::llm
    CHK["2 Code checks, flag only<br/>needs_review: currency, projection, cumulative"]:::code
    IMP["3 Importance score (code)<br/>size, FX, foreign, duration, related party"]:::code
    PM["4 Price reaction (code)<br/>abnormal return vs XU100"]:::code
    IDX["5 Similar earlier disclosures<br/>turkish-e5-large index"]:::code

    MORN["Morning list<br/>ranked, KONTROL ET for flagged, KAP link per item"]:::out

    SRC --> COL --> DB
    DB --> LLM --> CHK --> IMP --> MORN
    DB --> PM --> MORN
    DB --> IDX --> MORN
```

Purple = LLM, blue = data, grey = code, green = output.

## 2. Agent: answering an analyst's question (`agent.py`, LangGraph)

```mermaid
flowchart LR
    classDef llm fill:#8250df,stroke:#8250df,color:#ffffff
    classDef code fill:#2d333b,stroke:#768390,color:#ffffff
    classDef out fill:#1a7f37,stroke:#1a7f37,color:#ffffff

    Q(["Analyst question"]):::out
    ROUTE["Route (LLM)<br/>intent, symbol, date, topic"]:::llm
    VAL["Validate (code)<br/>ticker exists, date in range"]:::code
    T1["morning<br/>day's ranked list"]:::code
    T2["company<br/>last 12 months"]:::code
    T3["why_moved<br/>abnormal move + disclosures"]:::code
    T4["search<br/>top 5 by embedding"]:::code
    A(["Answer: numbers and KAP links from code"]):::out

    Q --> ROUTE --> VAL
    VAL --> T1 --> A
    VAL --> T2 --> A
    VAL --> T3 --> A
    VAL --> T4 --> A
```

The LLM only reads the question. It never writes a number or a link.

## Where the LLM is used, and where it is not

| Step | LLM? | Why |
|---|---|---|
| Field extraction from disclosure text | yes (`gemma4:e4b`) | Free Turkish text, many phrasings: rules alone got 12/15 on the dev set. |
| Contradiction checks, `needs_review` | no | Deterministic, unit-tested, cannot break other cases. |
| Importance score | no | Rules written in `docs/importance_score.md` before use. |
| Price reaction | no | Arithmetic on daily bars. |
| Search | embedding model, no generation | Finds documents; the answer lists them with KAP links. |
| Agent routing | yes | Reads the question only; code checks the route and computes the answer. |

This is the answer to "could it be solved without an LLM?": the LLM is used only where the input is free text.

## Measured (held-out, rule written before the run)

| Component | Result | Set |
|---|---|---|
| Extraction + code checks | silent errors 1/100 (95% upper bound 4.7%), flagged 11/100 | Set C, PASS |
| Search | recall@5 42/48 = 0.875, recall@1 32/48 = 0.667 | Set C questions |
| Latency | to be reported (per disclosure, per stage) | Set C run |

History: Set A (dev) 0/100 → Set B frozen v3 4/100 FAIL → code checks from the error analysis → Set C 1/100 PASS.

## Not measured (stated as limits)

- Importance score: rules are judgment, not fitted; no accuracy number.
- Agent routing: smoke test only; a router test set needs questions written by Feyza.
- Document-to-document similarity ("similar earlier disclosures"): no measured quality.
- Search ranks a same-company or same-region document above an exact proper-noun match; all 16 recall@1 misses on Set C were the right company. Next step: BM25 hybrid, measured on new questions.
- Similarity cannot say "no such disclosure": negative and answerable questions overlap.
- Disclosure texts come from apitest; `new_business` from prod.

## Why these choices

- **One doc per disclosure, no chunking:** median 52 words; 8 of 1273 docs are cut at 512 tokens.
- **numpy index instead of a vector database:** about 1.3k documents; a full rebuild takes about 33 s.
- **Local models:** licensed data must not leave the machine.
- **Collection on the Mac:** the server cannot reach Matriks (network block on their side, follow-up pending).
