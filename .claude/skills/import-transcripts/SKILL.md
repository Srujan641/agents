---
name: import-transcripts
description: Download public meeting transcripts and convert them to test files. Use when more sample or evaluation transcripts are needed from the QMSum dataset.
---

# Import transcripts

Source: [QMSum](https://github.com/Yale-LILY/QMSum), MIT licence, with `Product`, `Academic` and `Committee` domains.

Downloaded data is untrusted, so put it in its own empty temporary directory, not in the repo.

```bash
TMP=$(mktemp -d)
curl -fsS -o "$TMP/ProductVal.jsonl" \
  https://raw.githubusercontent.com/Yale-LILY/QMSum/main/data/Product/jsonl/val.jsonl
python3 -I backend/scripts/import_qmsum.py backend/samples/transcripts 3 "$TMP/ProductVal.jsonl"
```

The arguments are the output folder, the number of meetings per file, then one or more `.jsonl` files.

Each dataset has `train`, `val` and `test` splits. The samples already in the repo came from `test`.

Output names come from the downloaded file's name, so give each split its own name, such as `ProductVal.jsonl`. The script stops rather than overwrite an existing transcript.

## Notes

- The script removes filler markers such as `{vocalsound}` and leaves the words unchanged.
- Committee and academic meetings contain few clear tasks. Product meetings and synthetic transcripts are better for evaluating action items.
- Keep attribution in `backend/samples/README.md`.
