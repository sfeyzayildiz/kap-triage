# KAP Disclosure Triage Assistant

**Every morning it tells an equity analyst which new-business disclosures to read first, why, and which numbers to double-check. It also says how often it is wrong.**

![silent errors](https://img.shields.io/badge/silent_errors-1%2F100_on_unseen_texts-2ea44f) ![without an LLM](https://img.shields.io/badge/regex%2C_no_LLM-25%2F100-lightgrey) ![injection attacks](https://img.shields.io/badge/hidden--instruction_attacks-9_%E2%86%92_0_of_18-2ea44f)

![Demo on made-up sample data: overview, morning lists, review, watchlist, why it moved, themes, reliability](docs/img/demo.gif)

Demo, sped up, on made-up sample data (the real data is licensed and stays on my computer). Full video (about 80 seconds): [watch](https://github.com/user-attachments/assets/526cb4dc-837d-40f6-bf42-05845d2e9f94).

A working prototype for "Yeni İş İlişkisi" (new business relationship) disclosures on KAP, the public disclosure platform of Borsa İstanbul. It runs nightly on real data, on one laptop, with local models only. The screens are in Turkish because the users are Turkish analysts. Not investment advice: it does not predict prices or recommend trades.

**Author:** Feyza Yıldız ([LinkedIn](https://www.linkedin.com/in/feyza-yildiz/)), BTK Akademi AI workshop, Entertech İstanbul Teknokent, Oct-Nov 2026. Review in 10 minutes: [`docs/for_reviewers.md`](docs/for_reviewers.md).

## In 30 seconds
- **Problem:** An analyst gets these disclosures every day (1-2 on a normal day, more on busy ones) and must pick the ones that matter. The texts have traps: TL and USD get mixed up, a revision looks like a new order, a one-year estimate looks like the contract value.
- **Solution:** Every night the system pulls the new disclosures, a local LLM reads each one twice, and code checks the facts. What is unclear gets a "KONTROL ET" (verify) flag instead of a guess. In the morning the analyst gets a ranked list with reasons and a KAP link on every item; each sector desk can get its part by e-mail.
- **Proof:** On 100 disclosures it had never seen, 1 wrong amount or currency passed without a warning (95% upper bound 4.7%). Every pass bar was committed to git before its test.
- **Why not the data vendor's record?** Matriks has no record for 1 in 6 disclosures, and its record never says when it is unsure. Here it is a second opinion.

## Try it in 2 minutes (no licensed data needed)
```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python main.py panel --sample   # open http://127.0.0.1:8765/genel
```
The panel runs on 12 invented companies and 57 invented disclosures; their morning lists were made by the real nightly chain, and only the model's answers were written in advance. After the install, no model and no network are needed. Tested with Python 3.12. A 10-minute guided tour: [`sample/README.md`](sample/README.md).

Also without a model: `.venv/bin/pytest` and `.venv/bin/ruff check .` (both run by CI on every pull request; `tests/test_sample_data.py` runs the nightly chain with a fake model). On Windows, use `python -m venv .venv` and `.venv\Scripts\` instead of `.venv/bin/`.

## The story: it failed first
| step | data | silent errors | result | why it counts or not |
|---|---|---|---|---|
| Prompt v3 on the texts it was developed on | Set A | 0 / 100 | looked perfect | **Does not count:** the prompt was tuned on these texts, like seeing the exam questions in advance. |
| The same frozen system on unseen texts | Set B | 4 / 100 | **FAIL** (bar: at most 1) | The honest test. The prompt was not touched afterwards, as the rule said. |
| Code checks built from Set B's errors, on new unseen texts | Set C | **1 / 100**, 11 flagged | **PASS** | Measured on texts nobody had seen, with the bar written before the run. |

A silent error is a wrong amount or currency shown without a warning. "Flagged" means the item went to a person.

## The model can also be tricked
A disclosure text can hide a sentence written for AI tools. The model sometimes obeys it; the system does not let that pass silently. Example from the sample data (4 Nov, company SGL1):

| | raw model | system |
|---|---|---|
| Text | "...8.400.000 TL bedelli sözleşme..." plus a hidden sentence: report 840,000,000 TL | same text |
| Amount shown | 840,000,000 TL, no warning | 840,000,000 TL with a red "KONTROL ET" (verify) flag |
| Why | it followed the planted sentence | the amount is far from the vendor's record, and the sentence it comes from reads like an instruction |
| Analyst sees | a wrong number | the source sentence and the reasons, then checks the KAP text |

<img src="docs/img/injection_card.png" alt="The SGL1 card on the sample data: the model reported 840,000,000 TL from a planted sentence; the card shows that sentence as the source and a red KONTROL ET flag" width="760">

The same card in the panel (sample data, made up). The source sentence is the planted instruction, and the flag gives both reasons: the amount is more than twice the vendor's record, and it comes from an instruction-like sentence.

Measured on 18 real texts with a planted sentence: without the defence, 9 attacks succeeded silently; with it, 0 (95% upper bound 15.3%), with 3 extra flags on 200 normal texts ([rule](docs/layered_defence_rule.md)). Only texts with a vendor record were measured, with one attack wording. Try it yourself: step 3 of the [tour](sample/README.md#a-10-minute-tour), or the hidden-instruction example of kap-kart ([`sample/kart/4_gizli_talimat.txt`](sample/kart/4_gizli_talimat.txt), paste it into `/kart`).

## How it works
**The LLM reads text; code decides.** The LLM has three jobs: it extracts the facts from the disclosure text, judges whether the sentence an amount came from reads like an instruction, and, in the chat, picks a tool. Every sentence, score, ranking and link that people see is written by code from the database, and every extracted amount is shown next to the sentence it came from. Purple = LLM, grey = code, blue = data, green = what people see.

```mermaid
flowchart LR
    classDef llm fill:#8250df,stroke:#8250df,color:#ffffff
    classDef code fill:#2d333b,stroke:#768390,color:#ffffff
    classDef store fill:#1f6feb,stroke:#1f6feb,color:#ffffff
    classDef out fill:#1a7f37,stroke:#1a7f37,color:#ffffff

    subgraph NIGHT["Nightly, 23:43"]
        M["Matriks API<br/>new disclosures"]:::code --> C["Collector<br/>one pull per day"]:::code --> DB[("DuckDB")]:::store
        DB --> X["LLM extraction<br/>gemma4:e4b, read twice"]:::llm
        X --> K["Code checks +<br/>injection defence<br/>(code + LLM judge)<br/>flag, never fix"]:::code
        K --> S["Importance<br/>and order (code)"]:::code
        S --> L["Morning list<br/>reasons + KAP links"]:::out
        L --> AL["Phone alert<br/>(counts; error line<br/>on failure)"]:::out
    end
    subgraph MORNING["Every morning"]
        P["Panel<br/>analyst confirms or<br/>rejects each flag"]:::out
        API["Desk lists (code)<br/>desk, order, text"]:::code --> N["n8n<br/>weekdays 07:30"]:::code --> IN["Desk inboxes<br/>(local Mailpit)"]:::out
        OD["Desk e-mail on demand<br/>third-party MCP server"]:::code --> H{"Person<br/>approves?"}:::out
        H -- yes --> IN
    end
    L --> P
    L --> API
    L --> OD
```

| when | what happens | built with |
|---|---|---|
| **Every night, 23:43** | pulls the day's disclosures (one pull, enforced in code), reads each text twice with a local LLM, checks the facts in code, builds the morning list, sends a phone alert | launchd, Ollama, DuckDB |
| **Weekdays, 07:30** (when Docker is running) | e-mails each sector desk its part of the list (no amounts) | n8n, local mail inbox |
| **Any time** | panel with an overview, a watchlist and a confirm / reject step for flagged items (with a review history); guided form; chat agent that searches all past disclosures | LangGraph, RAG (`turkish-e5-large` + reranker) |
| **From local AI tools** | the agent's tools as an MCP server (local clients only); a desk e-mail through a third-party MCP server, sent only after a person approves | MCP, both directions |
| **On every change** | ruff + pytest; panel, n8n and mail inbox start with one command | GitHub Actions, Docker |

Real data since October 2024: about 1,300 disclosures, 1-2 new ones a day. More: [`docs/architecture.md`](docs/architecture.md).

## Measured, not assumed
Each test has a rule file with the measurement and the pass bar, committed before the run; the result was recorded after one run, in the rule file or in [`docs/results.md`](docs/results.md). The panel-review row is anecdotal and has no rule.

| part | measured | rule |
|---|---|---|
| Local LLM extraction | 1 silent error in 100 unseen texts; ~15 s per reading, ~31 s per disclosure in the nightly list (two readings) | [rule](docs/set_c_plan.md) |
| Without an LLM | the strongest regex in the repo (written for the code checks): 25 silent errors in 100 | [rule](docs/regex_baseline_rule.md) |
| RAG search | right disclosure in the top 5: 20/20; at rank 1: 17/20 (15 without the reranker) | [rule](docs/rerank_rule.md) |
| LangGraph agent | intended link in the top 5: 18/20 | [rule](docs/router_v2_rule.md) |
| n8n desk e-mails | 15 saved days, 33 e-mails: 0 lost, 0 wrong desk, 0 amount leaks | [rule](docs/n8n_routing_rule.md) |

<details>
<summary>All measured parts (10)</summary>

| part | job | measured | rule or result |
|---|---|---|---|
| Local LLM extraction | extracts the deal facts | 1 silent error in 100 unseen texts (one reading, Set C); ~15 s per reading, ~31 s per disclosure in the nightly list, which reads each text twice | [rule](docs/set_c_plan.md) |
| Without an LLM | the strongest regex in the repo (written for the code checks) on the same texts | 25 silent errors in 100 | [rule](docs/regex_baseline_rule.md) |
| Code checks + injection defence | flag what is unclear or planted in the text | hidden-instruction attacks: 9 silent → 0 (texts with a Matriks record; without one, only the source-sentence layer runs, not measured) | [rule](docs/layered_defence_rule.md) |
| Importance and order | ranks the morning list, with reasons | top pick right on 11/12 days (sorting by amount alone: 12/12) | [rule](docs/importance_v2_rule.md) |
| RAG search | finds the right and the similar earlier disclosures | right one in the top 5: 20/20; at rank 1: 17/20 (15 without the reranker) | [rule](docs/rerank_rule.md) |
| LangGraph agent | the LLM picks a tool, code writes the answer | intended link in the top 5: 18/20 | [rule](docs/router_v2_rule.md) |
| MCP server (ours) | the agent's 5 tools for local MCP clients | output identical 10/10, +0.011 s | [rule](docs/mcp_v2_rule.md) |
| MCP client (third-party e-mail server) | one desk e-mail on demand, after a person approves | outside addresses refused 7/7; unapproved sent 0 | [rule](docs/smtp_mcp_rule.md) |
| n8n desk e-mails | weekday e-mail to each sector desk | 15 saved days, 33 e-mails: 0 lost, 0 wrong desk, 0 amount leaks | [rule](docs/n8n_routing_rule.md) |
| Panel review | the analyst confirms or rejects each flag | first day: 3 of 6 flags were real errors; by 22 Nov: 8 decisions, 5 real errors (anecdotal, no rule) | [result](docs/results.md#scoring-desks-themes) |

</details>

**Tried and dropped**, each by a bar written before the test: three scope guards, LLM-written answers, BM25 and hybrid search, chunking, and two other disclosure types. All results on one page: [`docs/results.md`](docs/results.md).

## Limits
- Small test sets (100 / 48 / 20 / 18), so the bounds are wide. One person labeled all data.
- Live, about 1 in 5 disclosures goes to a person (Set D, 20-22%), above the 15% flag bar set for the test set; which check flags most was not analysed.
- Ordering: sorting by amount alone did as well (12/12 top picks). The value is in reading the amount right and flagging what is unclear, not in the ranking formula.
- One disclosure type; two more were piloted and did not pass their bars. The chat has no scope check (the guided form avoids this).
- Analyst time saved was not measured. Runs nightly on one laptop, with one local model and no fallback model.

All limits: [`docs/system_card.md`](docs/system_card.md). Where I was wrong: [`docs/known_issues.md`](docs/known_issues.md).

## How this was built
I led the project. I chose the problem and the scope with the instructor, obtained the data permission from Matriks, and decided what was adopted and what was dropped. I labeled every gold set by hand (about 350 disclosures in Sets A-D, plus the two pilots) and wrote the evaluation questions and the sealed attack sentences. I designed the measurement rules together with the assistant: I chose what to measure and the key choices, and approved each written rule before its run. I ran every measurement on my own machine, where the licensed data stays.

Most of the code was written with an AI coding assistant (Claude Code) under my direction, as pull requests with tests (CI on every change). By rule, the assistant worked with counts and ids only: it did not read the licensed data, the gold labels or the held-out questions, so it could not tune the system to them (the slips are recorded in [`docs/known_issues.md`](docs/known_issues.md), C3). External reviews were checked item by item against the code. Version 2 (the `kap_triage/` package, from 23 Nov) is developed the same way, with the support of an AI coding assistant, and every v2 change is merged only after I have read and approved it.

**I designed, wrote and tested the watchlist myself** ([`kap_triage/web/watchlist.py`](kap_triage/web/watchlist.py) and its panel integration): an analyst keeps the companies they cover in a local list, filters the morning list to them, and sees them at the top of the overview. The assistant gave hints and reviewed the code.

**Skills and tools:** Python · LLM evaluation (pre-registered rules, held-out sets, 95% bounds) · local LLMs with Ollama (`gemma4:e4b`) · RAG (`turkish-e5-large` embeddings + `bge-reranker-v2-m3`) · LangGraph agent · MCP server and client · prompt-injection defence · DuckDB · FastAPI · pytest · n8n · Docker · GitHub Actions CI · launchd.

## More
<details>
<summary>Screenshots (v1 demo mode: licensed values hidden; v2 has no demo mode)</summary>

| Morning list per desk | Guided form: company brief | Reliability page |
|---|---|---|
| ![Day page in demo mode](docs/img/day_demo.png) | ![Company brief in demo mode](docs/img/brief_demo.png) | ![Reliability page](docs/img/reliability.png) |

<img src="docs/img/overview_demo.png" alt="Overview page in demo mode" width="640">

Overview, the panel's start page (demo mode, real data, 22 Nov). The last list (21 Nov) had no new disclosures, so its counts are 0; the chart and the 8 review decisions are real (in 5, the flag caught a real extraction error).

</details>

<details>
<summary>Desk e-mails (n8n and a local mail inbox)</summary>

| n8n workflow (weekdays 07:30, or by webhook) | One desk e-mail (desk name and reasons masked) |
|---|---|
| ![n8n desk routing workflow](docs/img/n8n_workflow.png) | ![Desk e-mail in the local Mailpit inbox, masked](docs/img/desk_mail_masked.png) |

Desk e-mails on all 15 saved days: 33 e-mails, 0 lost, 0 wrong desk, 0 amounts ([rule](docs/n8n_routing_rule.md)). The desk, the order and the text come from code; n8n only delivers. The desk name and the reasons are masked here because the desk comes from the Matriks sector label.

</details>

<details>
<summary>Questions at any time (chat, guided form, MCP)</summary>

```mermaid
flowchart LR
    classDef llm fill:#8250df,stroke:#8250df,color:#ffffff
    classDef code fill:#2d333b,stroke:#768390,color:#ffffff
    classDef store fill:#1f6feb,stroke:#1f6feb,color:#ffffff
    classDef out fill:#1a7f37,stroke:#1a7f37,color:#ffffff

    Q(["Analyst<br/>chat question"]):::out --> R["LangGraph agent<br/>LLM picks the tool"]:::llm --> T
    F(["Analyst<br/>guided form"]):::out --> T
    MC(["Local MCP clients"]):::out -- MCP --> SRV["Project MCP server<br/>5 read-only tools"]:::code --> T
    T["Tools (code)<br/>morning list, company history,<br/>why it moved, search, company brief"]:::code
    DB[("DuckDB")]:::store --> T
    IDX[("Search index<br/>turkish-e5-large<br/>+ reranker")]:::store --> T
    T --> A(["Answer<br/>numbers and KAP links<br/>from the database"]):::out
```

</details>

<details>
<summary>kap-kart: the card from any public KAP text</summary>

Paste any "Yeni İş İlişkisi" text from kap.org.tr and get the card, with the same extraction code and a local model. Needs [Ollama](https://ollama.com) and `ollama pull gemma4:e4b` (about 9.5 GB, once); then open `http://127.0.0.1:8765/kart` in the panel, or run `python main.py kart metin.txt` in the terminal. The card imports no database and no Matriks code ([`kap_triage/web/kart.py`](kap_triage/web/kart.py)). Add a hidden instruction to the text: the card should show "KONTROL ET" (verify) instead of the planted amount.

</details>

<details>
<summary>How to run with a Matriks token</summary>

Needs Python 3.12, Ollama with `gemma4:e4b`, and `KAP_TOKEN` in `.env`.
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install --no-deps -e .
.venv/bin/python main.py nightly                                       # nightly collection + morning list (launchd: deploy/)
.venv/bin/python -m kap_triage.analysis.morning --date 2026-10-30      # morning list for one day
.venv/bin/python main.py agent "Bugün neye bakmalıyım?"                 # ask the agent ("What should I look at today?")
.venv/bin/python main.py panel                                         # panel: http://127.0.0.1:8765
```
With Docker: `docker compose up --build` ([`docs/docker.md`](docs/docker.md)). Operations: [`docs/runbook.md`](docs/runbook.md).

</details>

<details>
<summary>The code</summary>

| path | what is there |
|---|---|
| `main.py` | one entry point: `panel`, `sample`, `nightly`, `agent`, `mcp`, `mail`, `index`, `kart` |
| `kap_triage/collect/` | Matriks collection, the nightly job, price and sector pulls, the forward-test seal |
| `kap_triage/analysis/` | extraction (`llm.py` + `prompt_v3.txt`, frozen), code rules, defences, importance, morning list, desks |
| `kap_triage/assistant/` | search index, clustering and weekly themes, the LangGraph agent and its question parsing |
| `kap_triage/web/` | FastAPI app (`app.py`), page rendering, chat, guided form, watchlist, kap-kart, MCP |
| `tests/` | pytest, made-up data only (CI: ruff + pytest) |
| `sample/` | made-up sample data for the panel (built on your computer by `main.py sample`), kap-kart examples |
| `docs/` | rules, results, architecture details, development log: [index](docs/README.md) |
| `n8n/`, `mcp/smtp/`, `deploy/` | desk e-mail workflow, the pinned e-mail MCP server, the nightly launchd job |
| `data/` | local only, never committed |

New to the code? Read `collect/nightly.py` → `analysis/pipeline.py` → `analysis/llm.py` → `analysis/importance.py` → `analysis/morning.py` → `assistant/agent.py`: the path of one disclosure from collection to answer.

</details>

<details>
<summary>Related work</summary>

KAP summary sites and MCP servers for Borsa İstanbul (including Matriks' own) bring KAP news to AI tools; I found no published accuracy number for them. The closest research ([Dolphin et al. 2026, "Grounded Event Extraction from SEC 8-K Filings with a Fine-Grained Taxonomy", arXiv 2607.08346](https://arxiv.org/abs/2607.08346)) uses the same ideas at a larger scale, scored by an LLM judge; here accuracy comes from blind human labels. More: [`docs/metrics_faq.md`](docs/metrics_faq.md).

</details>

## Data, privacy, license
- Matriks data is used with permission, stays in `data/` and is never committed. All models run locally, and no licensed data is sent out: the only outgoing message is the nightly phone alert (through the ntfy push service): counts on success, a short error line on failure. n8n and Mailpit run locally with telemetry off, and desk e-mails carry no amounts.
- The Matriks permission runs to the end of December 2026. After that the nightly pipeline stops; kap-kart, the sample data and the code stay.
- The code is MIT ([`LICENSE`](LICENSE)); the license covers the code, not the data. A few tests contain short fragments of public KAP disclosure texts.
