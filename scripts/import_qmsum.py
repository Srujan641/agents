"""Convert QMSum .jsonl meetings into plain-text transcripts.

Usage: python scripts/import_qmsum.py OUT_DIR COUNT_PER_FILE FILE.jsonl [FILE.jsonl ...]
"""

import json
import re
import sys
from pathlib import Path

_NOISE = re.compile(r"\{[a-z_ ]+\}")


def main() -> None:
    out_dir, count, *sources = sys.argv[1:]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for source in map(Path, sources):
        with source.open(encoding="utf-8") as lines:
            for number, line in zip(range(1, int(count) + 1), lines, strict=False):
                turns = []
                for turn in json.loads(line)["meeting_transcripts"]:
                    content = " ".join(_NOISE.sub("", turn["content"]).split())
                    if content:
                        turns.append(f"{turn['speaker']}: {content}")
                name = f"qmsum_{source.stem.lower()}_{number:02d}.txt"
                (out_dir / name).write_text("\n".join(turns) + "\n", encoding="utf-8")
                print(f"{name}: {len(turns)} turns")


if __name__ == "__main__":
    main()
