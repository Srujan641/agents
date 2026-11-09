---
name: drive-watcher
description: Run or debug the transcript watcher and file parsers. Use when transcripts aren't being picked up, run twice, get stuck in processing, fail to parse, or when adding a file format.
---

# Drive watcher

Files: `backend/meeting_agent/watcher.py`, `drive.py`, `parsers.py`.

## Run

```bash
# Local folder in place of Drive. This calls OpenAI, at small cost.
SETTLE_SECONDS=0 DATABASE_PATH=/tmp/demo.db \
  uv run meeting-agent watch --once --local-folder backend/samples/transcripts

# Real Drive: needs DRIVE_FOLDER_ID and credentials.json
uv run meeting-agent watch
```

Use a throwaway `DATABASE_PATH` for experiments, because a processed file won't run again against the same database.

## Behaviour

| Situation | Result |
|---|---|
| Same file and revision | Skipped |
| Content edited | New revision, runs again |
| Changed within `SETTLE_SECONDS` | Waits for a later poll |
| Unreadable or empty | `failed`, not retried |
| Temporary error or crash | Retried after `STALE_AFTER_SECONDS`, up to `MAX_ATTEMPTS` in total |

Only files directly in the folder are read, not subfolders.

## Inspect

```bash
sqlite3 database/meeting_agent.db "select name,status,attempts,error from transcripts;"
```

If you ran with a throwaway `DATABASE_PATH`, query that file instead.

## Add a file format

Add the suffix to `_SUPPORTED_EXTENSIONS`, add a branch in `parse_transcript`, and raise `TranscriptParseError` for permanently bad files.
