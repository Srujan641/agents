---
name: connect-outputs
description: Add or debug Jira, Slack and Gmail delivery. Use when replacing the mock clients with real ones or when approved items aren't arriving.
---

# Outputs

File: `backend/meeting_agent/outputs.py`. Mocks are wired up in `service.py`.

Real clients are **not built yet**. `build_app` stops with an error if `USE_MOCK_INTEGRATIONS=false`.

## Add a real client

Implement the matching protocol, then choose it in `build_app`:

| Protocol | Method | Needs |
|---|---|---|
| `JiraClient` | `create_issue(ticket) -> str` | Site URL, email, API token, project key, issue type |
| `SlackClient` | `post_message(text) -> str` | Bot token with `chat:write`, channel ID, bot invited |
| `EmailClient` | `send(subject, body) -> str` | Gmail OAuth desktop client with the send scope |

## Watch for

- Jira assigns by account ID, so names must be mapped to account IDs. Leave a ticket unassigned if a name has no match.
- Sends go through `_send_once`, which records the returned ID. Return a real ID from every client.
- Only test against test accounts first, since these sends are visible to other people.
