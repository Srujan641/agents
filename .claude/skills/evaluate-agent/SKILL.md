---
name: evaluate-agent
description: Score the meeting agent against human-written AMI action items. Use when measuring precision or recall, tuning prompts against data, or rebuilding the evaluation set.
---

# Evaluate the agent

Files: `backend/evaluation/prepare_ami.py` and `run_eval.py`. Data goes in `backend/evaluation/data/`, ignored by git. Results go in `backend/evaluation/results/`.

## Build the data

```bash
TMP=$(mktemp -d)
curl -fsSL -o "$TMP/ami.zip" https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip
uv run python backend/evaluation/prepare_ami.py "$TMP/ami.zip" backend/evaluation/data backend/samples/transcripts
```

Annotations are CC BY 4.0, so credit the AMI corpus. Entries reading `NA` and meetings with no transcript words are excluded, which leaves 107 meetings: 21 for tuning and 86 for the test.

## Run

```bash
uv run python backend/evaluation/run_eval.py dev --label my-change
uv run python backend/evaluation/run_eval.py test --final
```

## Rules

- Tune only on `dev`. Reading test failures and then changing the agent makes the test score invalid.
- `test --final` refuses to run if `results/test_final.json` exists. To make a new official score, use new unseen meetings rather than deleting the file and rerunning.
- A ticket is correct if an LLM judge finds it describes the same task as a human reference item. The judge ignores owners and never sees the pipeline's reasoning.

## Reading the score

Human items come from short summaries, so real tasks they left out count as wrong. Precision here is a conservative figure. Report the real numbers, and describe what was measured.
