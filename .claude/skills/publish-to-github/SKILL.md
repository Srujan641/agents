---
name: publish-to-github
description: Update the README and push the meeting agent to GitHub. Use when the user asks to commit, push or publish.
---

# Publish to GitHub

Repo: https://github.com/Srujan641/agents, branch `main`. Only commit or push when the user asks.

## Steps

1. Update `README.md` so the status table matches reality. Say plainly what is untested.
2. Run `uv run ruff check .` and `uv run pytest -q`.
3. Scan every file git would publish for secrets. No output means none were found. This skill file is skipped because it contains the search patterns:
   ```bash
   { git ls-files; git ls-files -o --exclude-standard; } \
     | grep -v '^.claude/skills/publish-to-github/SKILL.md$' \
     | xargs -I{} grep -IlE 'sk-[A-Za-z0-9_-]{20,}|xoxb-[0-9]|ATATT|BEGIN PRIVATE KEY' {}
   ```
4. Confirm these are ignored: `git check-ignore .env credentials.json token_gmail.json`.
5. Stage files and read `git status --short` before committing. Don't include editor folders such as `.vscode/`.
6. Commit and push, then compare `git rev-parse HEAD` with `git ls-remote origin`.

## Metrics rule

Never put the 60%, 50% or 87.8% figures in the repo until the evaluation and timing runs have actually produced them. Report the measured numbers, even if they differ.
