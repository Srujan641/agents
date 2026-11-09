from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Jira rejects summaries that are over 255 characters or contain line breaks.
JiraSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255, pattern=r"^[^\r\n]+$"),
]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalStr = Annotated[str | None, BeforeValidator(_blank_to_none)]


class TranscriptStatus(StrEnum):
    PROCESSING = "processing"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Transcript(BaseModel):
    """A meeting transcript as plain text, ready for extraction."""

    file_id: str
    revision: str
    name: str
    text: NonBlankStr
    # Relative deadlines such as "by Friday" are resolved against this.
    meeting_date: date | None = None


class ActionItem(BaseModel):
    """One commitment extracted from a transcript."""

    model_config = ConfigDict(str_strip_whitespace=True)

    description: NonBlankStr
    # Verbatim transcript text. The hallucination filter checks it against the source.
    source_quote: NonBlankStr
    owner: OptionalStr = None
    # What was said ("by next Friday"), kept separate from the date resolved from it.
    deadline_text: OptionalStr = None
    deadline: date | None = None


class TicketDraft(BaseModel):
    """A Jira-ready ticket awaiting human approval."""

    model_config = ConfigDict(str_strip_whitespace=True)

    summary: JiraSummary
    description: NonBlankStr
    source_quote: NonBlankStr
    assignee: OptionalStr = None
    due_date: date | None = None
    priority: Priority = Priority.MEDIUM
    labels: list[str] = Field(default_factory=lambda: ["meeting-agent"])
