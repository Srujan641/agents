---
name: llm-cost-limit
description: The hard limit of $0.50 per OpenAI call. Use when calling the LLM, changing the model, updating prices, or adding any new LLM call.
---

# LLM cost limit

Rule from the project owner: **no call may exceed $0.50.**

All LLM calls must go through `GuardedLLM.parse` in `backend/meeting_agent/llm.py`. Never call the OpenAI client directly from pipeline code.

## How it holds

- Input is over-counted as prompt bytes plus schema bytes plus a margin.
- `max_completion_tokens` is set so the input and output together fit the limit, including reasoning tokens.
- If fewer than 1,000 output tokens are affordable, `CostLimitExceeded` is raised and nothing is sent.
- Models with no entry in `_PRICES` are refused.
- `Settings.max_cost_per_call_usd` has `le=0.5`, so a higher `.env` value stops the app from starting.
- The OpenAI client uses `max_retries=0`, so one call is one attempt.

## Change the model

1. Get its prices from OpenAI's pricing page.
2. Add it to `_PRICES`, using the long-context rates so the limit holds at any prompt size.
3. Set `OPENAI_MODEL` in `.env`.
4. Run `uv run pytest backend/tests/test_llm.py -q`.

This limits each call, not total spending, so keep a spending limit in the OpenAI billing settings too.
