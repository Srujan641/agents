---
name: quality-checks
description: Change duplicate detection, the hallucination filter or deadline validation. Use when bad tickets get through, good tickets are dropped, or deadlines resolve to the wrong date.
---

# Quality checks

File: `backend/meeting_agent/quality.py`. Tests: `backend/tests/test_quality.py`.

| Check | Function | Rule |
|---|---|---|
| Hallucination | `apply_grounding` | The quote must appear in the transcript, ignoring case, spacing and curly quotes |
| Owner | `_is_real_owner` | Group names are cleared, and the owner must appear in the transcript |
| Deadline text | `apply_grounding` | Cleared if not in the transcript |
| Deadline date | `resolve_deadline` | Resolved against the meeting date. Unknown, impossible, past or over 365 days away becomes empty |
| Duplicates | `remove_duplicates` | Keyword similarity of 0.7 or more, or the same quote with 0.4 or more. The same quote alone isn't enough, as one quote can hold two tasks |

The meeting date is the file's last-modified date. For old recordings or re-uploaded files, relative deadlines such as "next week" will therefore be resolved against the wrong day.

## Fix a failure

1. Find the case in the logs: search for `Rejected`.
2. Add it as a failing test using the real wording.
3. Change the rule and run `uv run pytest backend/tests/test_quality.py -q`.

Vague assurances and procedural statements need judgement, so they belong to the `verify` node rather than to a rule here.
