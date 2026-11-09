import sqlite3

import pytest
from meeting_agent.schemas import DraftStatus, TicketDraft, TranscriptStatus


def make_ticket(summary="Fix login"):
    return TicketDraft(summary=summary, description="Details", source_quote="Fix login.")


def test_transcript_is_claimed_only_once(storage):
    assert storage.claim_transcript("file-1", "rev-1", "standup.txt") is True
    assert storage.claim_transcript("file-1", "rev-1", "standup.txt") is False


def test_new_revision_of_a_file_can_be_claimed(storage):
    storage.claim_transcript("file-1", "rev-1", "standup.txt")
    assert storage.claim_transcript("file-1", "rev-2", "standup.txt") is True


def test_transcript_status_round_trip(storage):
    assert storage.get_transcript_status("file-1", "rev-1") is None
    storage.claim_transcript("file-1", "rev-1", "standup.txt")
    assert storage.get_transcript_status("file-1", "rev-1") is TranscriptStatus.PROCESSING
    storage.set_transcript_status("file-1", "rev-1", TranscriptStatus.FAILED, error="bad file")
    assert storage.get_transcript_status("file-1", "rev-1") is TranscriptStatus.FAILED


def test_set_status_on_unknown_transcript_raises(storage):
    with pytest.raises(KeyError):
        storage.set_transcript_status("missing", "rev-1", TranscriptStatus.FAILED)


def test_draft_needs_an_existing_transcript(storage):
    with pytest.raises(sqlite3.IntegrityError):
        storage.add_draft("missing", "rev-1", make_ticket())


def test_draft_starts_pending_and_saves_reviewer_edits(storage):
    storage.claim_transcript("file-1", "rev-1", "standup.txt")
    draft_id = storage.add_draft("file-1", "rev-1", make_ticket())
    assert [d.id for d in storage.list_drafts(DraftStatus.PENDING)] == [draft_id]

    storage.update_draft(draft_id, DraftStatus.APPROVED, make_ticket("Fix SSO login"))

    assert storage.list_drafts(DraftStatus.PENDING) == []
    approved = storage.list_drafts(DraftStatus.APPROVED)
    assert approved[0].ticket.summary == "Fix SSO login"


def test_update_unknown_draft_raises(storage):
    with pytest.raises(KeyError):
        storage.update_draft(999, DraftStatus.REJECTED)


def test_delivery_is_recorded_once(storage):
    assert storage.get_delivery("draft-1:jira") is None
    storage.record_delivery("draft-1:jira", "jira", "PROJ-1")
    assert storage.get_delivery("draft-1:jira") == "PROJ-1"
    with pytest.raises(sqlite3.IntegrityError):
        storage.record_delivery("draft-1:jira", "jira", "PROJ-2")
