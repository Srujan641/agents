import html
import io
import re
from pathlib import PurePath

from docx import Document
from docx.table import Table

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
_SUPPORTED_EXTENSIONS = {".txt", ".vtt", ".docx"}

_VOICE_TAG = re.compile(r"<v(?:\.[^\s>]*)?\s+([^>]+)>")
_ANY_TAG = re.compile(r"<[^>]+>")
_SPEAKER_PREFIX = re.compile(r"^([^:]{1,60}):\s+(.*)$", re.DOTALL)


class TranscriptParseError(Exception):
    """The file can never be parsed, so retrying won't help."""


def is_supported(name: str, mime_type: str) -> bool:
    return mime_type == GOOGLE_DOC_MIME or PurePath(name).suffix.lower() in _SUPPORTED_EXTENSIONS


def parse_transcript(name: str, mime_type: str, data: bytes) -> str:
    """Convert a downloaded file to plain text, with one speaker turn per line."""
    # Drive exports Google Docs as plain text, so they take the .txt path.
    suffix = ".txt" if mime_type == GOOGLE_DOC_MIME else PurePath(name).suffix.lower()
    if suffix == ".txt":
        text = _decode(data)
    elif suffix == ".vtt":
        text = _parse_vtt(_decode(data))
    elif suffix == ".docx":
        text = _parse_docx(data)
    else:
        raise TranscriptParseError(f"Unsupported file type: {name}")

    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise TranscriptParseError(f"No text found in {name}")
    return text


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _parse_vtt(text: str) -> str:
    """Handle Teams cues (<v Name>text</v>) and Zoom cues (Name: text)."""
    turns: list[tuple[str | None, str]] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip().splitlines()
        arrow = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if arrow is None:
            continue
        cue = " ".join(lines[arrow + 1 :])
        voice = _VOICE_TAG.search(cue)
        speaker = voice.group(1).strip() if voice else None
        cue = html.unescape(_ANY_TAG.sub("", cue)).strip()
        if speaker is None and (prefix := _SPEAKER_PREFIX.match(cue)):
            speaker, cue = prefix.group(1).strip(), prefix.group(2)
        if not cue:
            continue
        # A cue with no speaker carries on from the previous one.
        if turns and speaker in (None, turns[-1][0]):
            turns[-1] = (turns[-1][0], f"{turns[-1][1]} {cue}")
        else:
            turns.append((speaker, cue))
    return "\n".join(f"{speaker}: {cue}" if speaker else cue for speaker, cue in turns)


def _parse_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        lines: list[str] = []
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                for row in block.rows:
                    lines.append(": ".join(cell.text.strip() for cell in row.cells))
            else:
                lines.append(block.text)
    except Exception as exc:  # python-docx raises many types on a corrupt file
        raise TranscriptParseError(f"Could not read .docx file: {exc}") from exc
    return "\n".join(lines)
