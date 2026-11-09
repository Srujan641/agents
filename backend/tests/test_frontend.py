from pathlib import Path

import pytest
import streamlit as st
from meeting_agent import service
from meeting_agent.schemas import DraftStatus, TicketDraft, TranscriptStatus
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "frontend" / "app.py")


class FakePipeline:
    def __init__(self, storage):
        self.storage = storage
        self.finished = []
        self.error = None

    def finish_review(self, file_id, revision):
        self.finished.append((file_id, revision))
        if self.error:
            raise self.error
        self.storage.set_transcript_status(file_id, revision, TranscriptStatus.COMPLETED)


@pytest.fixture
def pipeline(storage, monkeypatch):
    fake = FakePipeline(storage)
    monkeypatch.setattr(service, "build_app", lambda settings: (storage, fake))
    st.cache_resource.clear()
    yield fake
    st.cache_resource.clear()


@pytest.fixture
def waiting(storage):
    storage.claim_transcript("f", "r", "standup.txt")
    storage.set_transcript_status("f", "r", TranscriptStatus.AWAITING_APPROVAL)
    ids = [
        storage.add_draft(
            "f", "r", TicketDraft(summary=s, description="Details", source_quote="Quote")
        )
        for s in ("Send budget", "Book room")
    ]
    return ids


def run():
    return AppTest.from_file(APP, default_timeout=30).run()


def test_empty_state(pipeline):
    app = run()
    assert not app.exception
    assert app.info[0].value == "No transcripts are waiting for review."


def test_every_item_must_be_decided(pipeline, waiting, storage):
    app = run()
    app.radio(key=f"draft-{waiting[0]}-decision").set_value("Approve")
    app.button[0].click().run()
    assert app.error
    assert pipeline.finished == []
    assert len(storage.list_drafts(DraftStatus.PENDING)) == 2


def test_approve_edit_and_reject(pipeline, waiting, storage):
    app = run()
    app.radio(key=f"draft-{waiting[0]}-decision").set_value("Approve")
    app.text_input(key=f"draft-{waiting[0]}-summary").set_value("Send final budget")
    app.radio(key=f"draft-{waiting[1]}-decision").set_value("Reject")
    app.button[0].click().run()

    assert not app.exception
    assert pipeline.finished == [("f", "r")]
    assert [d.ticket.summary for d in storage.list_drafts(DraftStatus.APPROVED)] == [
        "Send final budget"
    ]
    assert len(storage.list_drafts(DraftStatus.REJECTED)) == 1
    assert app.info[0].value == "No transcripts are waiting for review."


def test_invalid_edit_saves_and_sends_nothing(pipeline, waiting, storage):
    app = run()
    app.radio(key=f"draft-{waiting[0]}-decision").set_value("Approve")
    app.radio(key=f"draft-{waiting[1]}-decision").set_value("Approve")
    app.text_input(key=f"draft-{waiting[0]}-summary").set_value("   ")
    app.button[0].click().run()

    assert app.error
    assert pipeline.finished == []
    assert len(storage.list_drafts(DraftStatus.PENDING)) == 2


def test_failed_send_offers_a_retry(pipeline, waiting):
    pipeline.error = ConnectionError("Slack is down")  # stands in for detail the page must hide
    app = run()
    for draft_id in waiting:
        app.radio(key=f"draft-{draft_id}-decision").set_value("Approve")
    app.button[0].click().run()
    assert "Sending failed" in app.error[0].value
    assert "Slack is down" not in app.error[0].value

    pipeline.error = None
    app = run()
    app.button(key="retry-f-r").click().run()
    assert len(pipeline.finished) == 2
    assert app.info[0].value == "No transcripts are waiting for review."
