# Agent routing: LLM router vs. a keyword router (rule written before the questions)

Date: 2026-11-10. Committed together with the keyword router (`scripts/route_eval.py: rule_route`) **before** Feyza writes any question.

## Question
The agent's only LLM step reads the analyst's question and picks one tool (`morning`, `company`, `why_moved`, `search`, `unknown`) plus a ticker and a date. Code then validates the route (`agent.validate`). Could a few keyword rules do the same? This is the instructor's "could it be solved without an LLM?" for the agent.

## Questions (Feyza)
- 20 new questions written by Feyza with `scripts/write_route_questions.py`, 4 per intent, each with the intended tool and, for `company` / `why_moved`, the intended ticker. Mixed wording: some with the ticker written, some with only the company name, some with dates in words.
- Written after this rule and the keyword router are committed; Claude does not propose questions.

## Measurement (run by Feyza, once)
`scripts/route_eval.py --run` routes each question with both routers, each followed by the same `agent.validate` (real context: tickers in the database, last disclosure day, last price day). Stored: intent and symbol per router; stdout: counts only.
- **Primary:** intent accuracy after validation, out of 20.
- **Secondary:** ticker accuracy on the `company` / `why_moved` questions; median routing seconds.

## Decision
- **Keep the LLM router** if its intent accuracy is **at least 2 questions higher** than the keyword router.
- Otherwise **switch the agent to the keyword router** (cheaper, deterministic, no model call), and say so in the presentation.
- Also reported: if the LLM router is below 16/20, the agent's routing is called weak in the limits, whatever the comparison.

## Honest limits
- 20 questions, one author; the keyword router was written by Claude without seeing them, but by someone who knows the tools.
- Only the route is measured, not the tool answers (those are code and are tested by the self-tests).
