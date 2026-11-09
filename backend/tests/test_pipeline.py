import sqlite3
from datetime import date

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from meeting_agent.outputs import Outputs
from meeting_agent.pipeline import (
    ReviewError,
    TranscriptPipeline,
    _ExtractedItem,
    _Extraction,
    _Verdict,
    _Verdicts,
    draft_ticket,
    split_into_chunks,
)
from meeting_agent.schemas import ActionItem, DraftStatus, Transcript, TranscriptStatus

TEXT = "Ana: I'll send the budget by Friday. Ben: I'll book the room."


class FakeLLM:
    def __init__(self, *extractions, reject=()):
        self.extractions = list(extractions)
        self.reject = set(reject)
        self.prompts = []
        self.skip_verdicts = False

    def parse(self, system, user, schema):
        if schema is _Verdicts:
            count = user.count('"index"')
            indexes = [] if self.skip_verdicts else range(count)
            return _Verdicts(
                verdicts=[_Verdict(index=i, keep=i not in self.reject, reason="r") for i in indexes]
            )
        self.prompts.append(user)
        return self.extractions.pop(0)


class FakeOutputs:
    def __init__(self):
        self.issues, self.slack, self.emails = [], [], []
        self.fail_slack = False

    def create_issue(self, ticket):
        self.issues.append(ticket)
        return f"PROJ-{len(self.issues)}"

    def post_message(self, text):
        if self.fail_slack:
            raise ConnectionError("Slack is down")
        self.slack.append(text)
        return "slack-1"

    def send(self, subject, body):
        self.emails.append((subject, body))
        return "email-1"

    def bundle(self):
        return Outputs(jira=self, slack=self, email=self)


def extracted(description="Send the budget", quote="I'll send the budget by Friday.", owner="Ana"):
    return _ExtractedItem(
        description=description, source_quote=quote, owner=owner, deadline_text="by Friday"
    )


def two_items():
    return _Extraction(
        items=[extracted(), extracted("Book the room", "I'll book the room.", "Ben")]
    )


def make_transcript(text=TEXT):
    return Transcript(
        file_id="f", revision="r", name="standup.txt", text=text, meeting_date=date(2026, 11, 4)
    )


@pytest.fixture
def outputs():
    return FakeOutputs()


@pytest.fixture
def make_pipeline(storage, outputs):
    storage.claim_transcript("f", "r", "standup.txt")

    def build(llm, checkpointer=None):
        return TranscriptPipeline(llm, storage, outputs.bundle(), checkpointer or InMemorySaver())

    return build


def decide(storage, status=DraftStatus.APPROVED):
    for draft in storage.list_drafts(DraftStatus.PENDING):
        storage.update_draft(draft.id, status)


def test_short_text_is_one_chunk():
    assert split_into_chunks("a b\nc d") == ["a b\nc d"]


def test_chunks_respect_limit_keep_order_and_overlap():
    lines = [f"line{i} word word word word" for i in range(100)]
    chunks = split_into_chunks("\n".join(lines), max_words=50, overlap_words=10)
    assert len(chunks) > 1
    assert all(len(chunk.split()) <= 50 for chunk in chunks)
    assert chunks[1].splitlines()[0] in chunks[0].splitlines()
    assert {line for chunk in chunks for line in chunk.splitlines()} == set(lines)


def test_oversized_single_line_is_kept_whole():
    long_line = " ".join(["word"] * 100)
    chunks = split_into_chunks(f"a\n{long_line}\nb", max_words=10, overlap_words=1)
    assert any(long_line in chunk.splitlines() for chunk in chunks)


def test_draft_ticket_carries_source_and_owner():
    item = ActionItem(
        description="Send\nthe budget", source_quote="Quote", owner="Ana", deadline_text="Friday"
    )
    ticket = draft_ticket(item, "standup.txt")
    assert ticket.summary == "Send the budget"
    assert ticket.assignee == "Ana"
    assert "standup.txt" in ticket.description and "Friday" in ticket.description


def test_run_pauses_for_approval_and_sends_nothing(storage, outputs, make_pipeline):
    status = make_pipeline(FakeLLM(two_items()))(make_transcript())

    assert status is TranscriptStatus.AWAITING_APPROVAL
    assert len(storage.list_drafts(DraftStatus.PENDING)) == 2
    assert storage.list_drafts(DraftStatus.PENDING)[0].ticket.due_date == date(2026, 11, 6)
    assert (outputs.issues, outputs.slack, outputs.emails) == ([], [], [])


def test_transcript_with_no_tasks_is_complete(make_pipeline):
    pipeline = make_pipeline(FakeLLM(_Extraction(items=[])))
    assert pipeline(make_transcript()) is TranscriptStatus.COMPLETED


def test_malformed_and_ungrounded_items_are_dropped(storage, make_pipeline):
    answer = _Extraction(
        items=[
            extracted(quote="   "),
            extracted(quote="A sentence nobody said."),
            extracted("Book the room", "I'll book the room.", "Ben"),
        ]
    )
    make_pipeline(FakeLLM(answer))(make_transcript())
    assert [d.ticket.summary for d in storage.list_drafts()] == ["Book the room"]


def test_items_the_reviewer_rejects_or_skips_are_dropped(storage, make_pipeline):
    make_pipeline(FakeLLM(two_items(), reject=[0]))(make_transcript())
    assert [d.ticket.summary for d in storage.list_drafts()] == ["Book the room"]

    llm = FakeLLM(two_items())
    llm.skip_verdicts = True
    assert make_pipeline(llm)(make_transcript()) is TranscriptStatus.COMPLETED
    assert storage.list_drafts() == []


def test_retry_does_not_duplicate_drafts(storage, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items(), two_items()))
    pipeline(make_transcript())
    pipeline(make_transcript())
    assert len(storage.list_drafts()) == 2


def test_every_chunk_is_sent_to_the_model(make_pipeline):
    text = "\n".join(" ".join(["word"] * 1000) for _ in range(10))
    llm = FakeLLM(_Extraction(items=[]), _Extraction(items=[]))
    make_pipeline(llm)(make_transcript(text))
    assert len(llm.prompts) == 2


def test_review_cannot_finish_with_undecided_drafts(outputs, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items()))
    pipeline(make_transcript())
    with pytest.raises(ReviewError):
        pipeline.finish_review("f", "r")
    assert outputs.issues == []


def test_only_approved_items_are_sent_with_reviewer_edits(storage, outputs, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items()))
    pipeline(make_transcript())
    first, second = storage.list_drafts(DraftStatus.PENDING)
    edited = first.ticket.model_copy(update={"summary": "Send the final budget"})
    storage.update_draft(first.id, DraftStatus.APPROVED, edited)
    storage.update_draft(second.id, DraftStatus.REJECTED)

    pipeline.finish_review("f", "r")

    assert [t.summary for t in outputs.issues] == ["Send the final budget"]
    assert "Send the final budget" in outputs.slack[0]
    assert "Book the room" not in outputs.slack[0] + outputs.emails[0][1]
    assert storage.get_transcript_status("f", "r") is TranscriptStatus.COMPLETED


def test_rejecting_everything_sends_nothing(storage, outputs, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items()))
    pipeline(make_transcript())
    decide(storage, DraftStatus.REJECTED)
    pipeline.finish_review("f", "r")
    assert (outputs.issues, outputs.slack, outputs.emails) == ([], [], [])


def test_failed_send_can_be_retried_without_duplicates(storage, outputs, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items()))
    pipeline(make_transcript())
    decide(storage)
    outputs.fail_slack = True
    with pytest.raises(ConnectionError):
        pipeline.finish_review("f", "r")
    assert len(outputs.issues) == 2
    assert storage.get_transcript_status("f", "r") is not TranscriptStatus.COMPLETED

    outputs.fail_slack = False
    pipeline.finish_review("f", "r")
    assert len(outputs.issues) == 2
    assert len(outputs.slack) == len(outputs.emails) == 1


def test_finished_review_cannot_send_again(storage, outputs, make_pipeline):
    pipeline = make_pipeline(FakeLLM(two_items()))
    pipeline(make_transcript())
    decide(storage)
    pipeline.finish_review("f", "r")
    with pytest.raises(ReviewError):
        pipeline.finish_review("f", "r")
    assert len(outputs.issues) == 2


def test_approval_survives_a_restart(tmp_path, storage, outputs, make_pipeline):
    path = tmp_path / "checkpoints.db"

    def saver():
        checkpointer = SqliteSaver(sqlite3.connect(path, check_same_thread=False))
        checkpointer.setup()
        return checkpointer

    make_pipeline(FakeLLM(two_items()), saver())(make_transcript())
    decide(storage)

    make_pipeline(FakeLLM(), saver()).finish_review("f", "r")
    assert len(outputs.issues) == 2
