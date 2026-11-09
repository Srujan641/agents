import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from meeting_agent.schemas import TicketDraft

logger = logging.getLogger(__name__)


class JiraClient(Protocol):
    def create_issue(self, ticket: TicketDraft) -> str: ...


class SlackClient(Protocol):
    def post_message(self, text: str) -> str: ...


class EmailClient(Protocol):
    def send(self, subject: str, body: str) -> str: ...


@dataclass(frozen=True)
class Outputs:
    jira: JiraClient
    slack: SlackClient
    email: EmailClient


class MockJira:
    def create_issue(self, ticket: TicketDraft) -> str:
        issue = f"MOCK-{uuid.uuid4().hex[:8]}"
        logger.info("[mock jira] %s: %s", issue, ticket.summary)
        return issue


class MockSlack:
    def post_message(self, text: str) -> str:
        logger.info("[mock slack] %s", text)
        return f"mock-slack-{uuid.uuid4().hex[:8]}"


class MockEmail:
    def send(self, subject: str, body: str) -> str:
        logger.info("[mock email] %s", subject)
        return f"mock-email-{uuid.uuid4().hex[:8]}"


def mock_outputs() -> Outputs:
    return Outputs(jira=MockJira(), slack=MockSlack(), email=MockEmail())
