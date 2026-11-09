---
name: approval-flow
description: Run or change the human approval page and the pause and resume logic. Use when working on the Streamlit page, reviewing drafts, or debugging runs stuck waiting for approval.
---

# Approval flow

Files: `frontend/app.py`, and `finish_review` in `backend/meeting_agent/pipeline.py`.

## Run

```bash
uv run streamlit run frontend/app.py --server.address 127.0.0.1
```

To review a throwaway run, start the page with the same `DATABASE_PATH` used for the watcher.

Keep it on `127.0.0.1`. The page has no login, and anyone who can reach it can approve tickets.

## Rules

- Nothing may send without approval. The only graph path to `deliver` goes through `approval`.
- `_approval` must only call `interrupt`, because LangGraph re-runs that node on resume.
- `finish_review` refuses while any draft is still pending.
- `deliver` reads approved drafts from the database, so reviewer edits are what get sent.
- Runs pause in `database/checkpoints.db`, so they survive restarts.

## Retry after a failed send

The page shows **Retry sending**. Delivery keys prevent repeats of anything already sent.

## Test

`uv run pytest backend/tests/test_frontend.py -q` drives the page with Streamlit's `AppTest`.
