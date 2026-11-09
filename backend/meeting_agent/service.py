import sqlite3

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from openai import OpenAI

from meeting_agent import schemas
from meeting_agent.config import Settings
from meeting_agent.llm import GuardedLLM
from meeting_agent.outputs import mock_outputs
from meeting_agent.pipeline import TranscriptPipeline
from meeting_agent.storage import Storage

# The types saved in graph checkpoints, which LangGraph must be told are safe to load.
_STATE_TYPES = [
    (schemas.__name__, name) for name in ("ActionItem", "Priority", "TicketDraft", "Transcript")
]


class SetupError(Exception):
    """A required setting is missing."""


def checkpoint_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_STATE_TYPES)


def build_llm(settings: Settings) -> GuardedLLM:
    if settings.openai_api_key is None or not settings.openai_model:
        raise SetupError("Set OPENAI_API_KEY and OPENAI_MODEL in .env.")
    return GuardedLLM(
        OpenAI(api_key=settings.openai_api_key.get_secret_value(), max_retries=0, timeout=300),
        settings.openai_model,
        max_cost_usd=settings.max_cost_per_call_usd,
        max_output_tokens=settings.max_output_tokens,
    )


def build_app(settings: Settings) -> tuple[Storage, TranscriptPipeline]:
    if not settings.use_mock_integrations:
        raise SetupError("Real Jira, Slack and Gmail aren't connected yet. Keep the mocks on.")
    storage = Storage(settings.database_path)
    connection = sqlite3.connect(
        settings.database_path.with_name("checkpoints.db"), check_same_thread=False
    )
    checkpointer = SqliteSaver(connection, serde=checkpoint_serde())
    checkpointer.setup()
    return storage, TranscriptPipeline(build_llm(settings), storage, mock_outputs(), checkpointer)
