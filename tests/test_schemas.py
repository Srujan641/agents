from datetime import date

import pytest
from pydantic import ValidationError

from meeting_agent.schemas import ActionItem, Priority, TicketDraft


def test_action_item_keeps_extracted_fields():
    item = ActionItem(
        description="Send the budget to finance",
        source_quote="Priya: I'll send the budget to finance by Friday.",
        owner="Priya",
        deadline_text="by Friday",
        deadline="2026-11-06",
    )
    assert item.owner == "Priya"
    assert item.deadline == date(2026, 11, 6)


def test_action_item_requires_a_source_quote():
    with pytest.raises(ValidationError):
        ActionItem(description="Send the budget")
    with pytest.raises(ValidationError):
        ActionItem(description="Send the budget", source_quote="   ")


def test_action_item_turns_blank_owner_into_none():
    item = ActionItem(description="Fix login", source_quote="We should fix login.", owner="  ")
    assert item.owner is None


def test_action_item_rejects_impossible_date():
    with pytest.raises(ValidationError):
        ActionItem(description="Fix login", source_quote="Fix login.", deadline="2026-02-30")


def test_ticket_draft_defaults():
    ticket = TicketDraft(summary="Fix login", description="Details", source_quote="Fix login.")
    assert ticket.priority is Priority.MEDIUM
    assert ticket.labels == ["meeting-agent"]


@pytest.mark.parametrize("summary", ["", "x" * 256, "two\nlines"])
def test_ticket_draft_rejects_summaries_jira_would_reject(summary):
    with pytest.raises(ValidationError):
        TicketDraft(summary=summary, description="Details", source_quote="Quote.")
