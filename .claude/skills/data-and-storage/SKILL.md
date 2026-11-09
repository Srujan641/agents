---
name: data-and-storage
description: Change the meeting agent's data formats, settings or SQLite storage. Use when adding fields to ActionItem, TicketDraft or Transcript, adding a setting, or changing how runs, drafts and deliveries are saved.
---

# Data formats and storage

| File | Holds |
|---|---|
| `backend/meeting_agent/schemas.py` | Pydantic models and status enums |
| `backend/meeting_agent/config.py` | Settings read from `.env` |
| `backend/meeting_agent/storage.py` | All SQLite access |
| `database/schema.sql` | Table definitions |

## Guarantees to keep

- `ActionItem.source_quote` is required, because the hallucination filter depends on it.
- `TicketDraft.summary` stays within Jira's rules: 1 to 255 characters and one line.
- `claim_transcript` returns True only once per file and revision. This is what prevents repeat runs.
- `replace_drafts` deletes and inserts in one transaction, so a retried run can't leave duplicates.
- `get_delivery` and `record_delivery` prevent double sends.

## Steps

1. Change the model or table.
2. Add the setting to both `config.py` and `.env.example`.
3. If a model saved in checkpoints gains a new class, add it to `_STATE_TYPES` in `service.py`, otherwise LangGraph can't load it safely.
4. Run `uv run pytest -q`.
