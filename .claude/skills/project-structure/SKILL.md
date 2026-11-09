---
name: project-structure
description: Where code belongs in the meeting agent. Use before adding or moving any file, or when imports, paths or the package layout break.
---

# Project structure

```text
backend/meeting_agent/   Python package: all agent logic
backend/tests/           pytest suite
backend/scripts/         one-off data tools
backend/samples/         sample transcripts
frontend/app.py          Streamlit approval page
database/schema.sql      SQLite tables
database/*.db            local data, ignored by git
.claude/skills/          these skills
```

## Rules

- Logic goes in `backend/meeting_agent/`. `frontend/app.py` only displays things and calls the backend.
- Change tables in `database/schema.sql`, never inline in Python. `CREATE TABLE IF NOT EXISTS` won't alter an existing table, so delete local `database/*.db` files after changing a table during development.
- `pyproject.toml` stays at the root and points uv at the package with `module-root = "backend"`.
- `storage.py` finds the schema relative to its own path, so keep `backend/` and `database/` as siblings.
- Secrets go only in `.env`, `credentials*.json` or `token*.json`, all ignored by git.

## Check after any move

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run pytest -q
```
