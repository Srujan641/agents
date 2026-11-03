import io

import pytest
from docx import Document

from meeting_agent.parsers import (
    GOOGLE_DOC_MIME,
    TranscriptParseError,
    is_supported,
    parse_transcript,
)


@pytest.mark.parametrize(
    ("name", "mime", "expected"),
    [
        ("a.txt", "text/plain", True),
        ("A.VTT", "text/vtt", True),
        ("a.docx", "application/octet-stream", True),
        ("Meeting notes", GOOGLE_DOC_MIME, True),
        ("a.pdf", "application/pdf", False),
        ("folder", "application/vnd.google-apps.folder", False),
    ],
)
def test_is_supported(name, mime, expected):
    assert is_supported(name, mime) is expected


def test_txt_drops_blank_lines_and_bom():
    data = "﻿Ana: Hello\n\n   \nBen: Hi  \n".encode()
    assert parse_transcript("a.txt", "text/plain", data) == "Ana: Hello\nBen: Hi"


def test_txt_falls_back_for_non_utf8():
    assert parse_transcript("a.txt", "text/plain", "Café".encode("cp1252")) == "Café"


def test_google_doc_is_read_as_exported_text():
    assert parse_transcript("Notes", GOOGLE_DOC_MIME, b"Ana: Hello") == "Ana: Hello"


def test_vtt_teams_format_merges_same_speaker():
    data = b"""WEBVTT

NOTE this is a comment

abc-1
00:00:01.000 --> 00:00:02.000
<v Ana Ruiz>I'll send</v>

abc-2
00:00:02.000 --> 00:00:03.000
<v Ana Ruiz>the budget &amp; plan.</v>

00:00:03.000 --> 00:00:04.000
<v Ben>Thanks.</v>
"""
    assert parse_transcript("a.vtt", "text/vtt", data) == (
        "Ana Ruiz: I'll send the budget & plan.\nBen: Thanks."
    )


def test_vtt_zoom_format_and_unlabelled_continuation():
    data = b"""WEBVTT

1
00:00:01.000 --> 00:00:02.000
Ana: I'll send it

2
00:00:02.000 --> 00:00:03.000
by Friday.

3
00:00:03.000 --> 00:00:04.000
Ben: Great.
"""
    assert (
        parse_transcript("a.vtt", "text/vtt", data) == "Ana: I'll send it by Friday.\nBen: Great."
    )


def test_docx_reads_paragraphs_and_tables_in_order():
    document = Document()
    document.add_paragraph("Ana: Hello")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Ben"
    table.cell(0, 1).text = "Hi"
    document.add_paragraph("Ana: Bye")
    buffer = io.BytesIO()
    document.save(buffer)

    assert parse_transcript("a.docx", "application/octet-stream", buffer.getvalue()) == (
        "Ana: Hello\nBen: Hi\nAna: Bye"
    )


@pytest.mark.parametrize(
    ("name", "data"),
    [("a.docx", b"not a zip"), ("a.txt", b"  \n \n"), ("a.vtt", b"WEBVTT\n"), ("a.pdf", b"%PDF")],
)
def test_unreadable_files_raise_parse_error(name, data):
    with pytest.raises(TranscriptParseError):
        parse_transcript(name, "application/octet-stream", data)
