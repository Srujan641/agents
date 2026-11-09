"""Build evaluation transcripts and human answers from the AMI corpus annotations.

Usage: python prepare_ami.py ANNOTATIONS.zip OUT_DIR [SEEN_TRANSCRIPT_DIR ...]

Download ANNOTATIONS.zip from
https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip
Meetings resembling files in SEEN_TRANSCRIPT_DIR go in the dev split, so the test split stays
unseen during tuning.
"""

import html
import json
import random
import re
import sys
import zipfile
from pathlib import Path

_WORD = re.compile(r'<w [^>]*starttime="([\d.]+)"[^>]*?(punc="true")?[^>]*>([^<]*)</w>')
_ACTIONS = re.compile(r"<actions.*?</actions>", re.DOTALL)
_SENTENCE = re.compile(r"<sentence[^>]*>(.*?)</sentence>", re.DOTALL)
_SPEAKER = re.compile(r'nxt_agent="([A-Z])"[^>]*role="([A-Z]+)"')
_MEETING = re.compile(r'<meeting [^>]*observation="(\w+)".*?</meeting>', re.DOTALL)
_ROLES = {
    "PM": "Project Manager",
    "ME": "Marketing Expert",
    "UI": "User Interface Designer",
    "ID": "Industrial Designer",
}
_NOT_ANNOTATED = re.compile(r"\W*n\W*a\W*", re.IGNORECASE)
_PAUSE_SECONDS = 0.75
_DEV_SIZE = 21
_SEED = 42
_SEEN_SIMILARITY = 0.5


def read(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("latin-1")


def speaker_utterances(xml: str, label: str) -> list[tuple[float, str, str]]:
    utterances: list[tuple[float, str, str]] = []
    start = previous = 0.0
    words: list[str] = []
    for match in _WORD.finditer(xml):
        time, is_punctuation, text = float(match[1]), match[2], html.unescape(match[3])
        if is_punctuation and words:
            words[-1] += text
            continue
        if words and time - previous > _PAUSE_SECONDS:
            utterances.append((start, label, " ".join(words)))
            words = []
        if not words:
            start = time
        words.append(text)
        previous = time
    if words:
        utterances.append((start, label, " ".join(words)))
    return utterances


def build_transcript(archive: zipfile.ZipFile, meeting: str, speakers: dict[str, str]) -> str:
    utterances: list[tuple[float, str, str]] = []
    for letter, label in speakers.items():
        name = f"words/{meeting}.{letter}.words.xml"
        if name in archive.namelist():
            utterances.extend(speaker_utterances(read(archive, name), label))
    turns: list[list[str]] = []
    for _, label, text in sorted(utterances, key=lambda item: item[0]):
        if turns and turns[-1][0] == label:
            turns[-1][1] += f" {text}"
        else:
            turns.append([label, text])
    return "\n".join(f"{label}: {text}" for label, text in turns) + "\n"


def word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def main() -> None:
    zip_path, out_dir, *seen_dirs = sys.argv[1:]
    out_dir = Path(out_dir)
    (out_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    gold: dict[str, list[str]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        speakers_by_meeting = {}
        for match in _MEETING.finditer(read(archive, "corpusResources/meetings.xml")):
            found = _SPEAKER.findall(match[0])
            speakers_by_meeting[match[1]] = {
                letter: _ROLES.get(role, f"Speaker {letter}") for letter, role in found
            }
        for name in sorted(n for n in archive.namelist() if n.endswith(".abssumm.xml")):
            meeting = Path(name).name.split(".")[0]
            block = _ACTIONS.search(read(archive, name))
            actions = _SENTENCE.findall(block[0]) if block else []
            actions = [" ".join(html.unescape(a).split()) for a in actions]
            # Annotators wrote "NA" where they had nothing to record.
            actions = [a for a in actions if a and not _NOT_ANNOTATED.fullmatch(a)]
            if actions and meeting in speakers_by_meeting:
                text = build_transcript(archive, meeting, speakers_by_meeting[meeting])
                if not text.strip():
                    print(f"Skipped {meeting}: no transcript words in the annotations")
                    continue
                gold[meeting] = actions
                (out_dir / "transcripts" / f"{meeting}.txt").write_text(text, encoding="utf-8")

    words = {m: word_set((out_dir / "transcripts" / f"{m}.txt").read_text()) for m in gold}
    seen: set[str] = set()
    for path in (p for folder in seen_dirs for p in Path(folder).glob("qmsum_product*.txt")):
        sample = word_set(path.read_text(encoding="utf-8"))
        best = max(words, key=lambda m: len(words[m] & sample) / len(words[m] | sample))
        if len(words[best] & sample) / len(words[best] | sample) >= _SEEN_SIMILARITY:
            seen.add(best)

    unseen = sorted(set(gold) - seen)
    random.Random(_SEED).shuffle(unseen)
    extra_dev = max(0, _DEV_SIZE - len(seen))
    dev = sorted(seen | set(unseen[:extra_dev]))
    test = sorted(unseen[extra_dev:])
    (out_dir / "gold.json").write_text(json.dumps(gold, indent=1), encoding="utf-8")
    (out_dir / "split.json").write_text(json.dumps({"dev": dev, "test": test}, indent=1))
    print(f"meetings={len(gold)} actions={sum(map(len, gold.values()))}")
    print(f"seen={sorted(seen)}")
    print(f"dev={len(dev)} test={len(test)}")


if __name__ == "__main__":
    main()
