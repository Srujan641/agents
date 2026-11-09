import json
from types import SimpleNamespace

import pytest
from meeting_agent.config import Settings
from meeting_agent.llm import CostLimitExceeded, GuardedLLM, LLMResponseError
from pydantic import BaseModel


class Answer(BaseModel):
    value: str


class FakeClient:
    def __init__(self, finish_reason="stop", parsed=None, refusal=None):
        self.calls = []
        self.response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000),
            choices=[
                SimpleNamespace(
                    finish_reason=finish_reason,
                    message=SimpleNamespace(parsed=parsed, refusal=refusal),
                )
            ],
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def make_llm(client, max_cost=0.5, max_output=16000):
    return GuardedLLM(client, "gpt-6-luna", max_cost_usd=max_cost, max_output_tokens=max_output)


def worst_case_cost(call):
    prompt_bytes = (
        sum(len(m["content"].encode()) for m in call["messages"])
        + len(json.dumps(Answer.model_json_schema()).encode())
        + 500
    )
    return (prompt_bytes * 0.20 + call["max_completion_tokens"] * 0.75) / 1_000_000


def test_normal_call_uses_the_configured_output_limit():
    client = FakeClient(parsed=Answer(value="ok"))
    assert make_llm(client).parse("sys", "user", Answer).value == "ok"
    assert client.calls[0]["max_completion_tokens"] == 16000


@pytest.mark.parametrize("prompt_size", [0, 500_000, 2_000_000])
def test_sent_calls_can_never_exceed_the_limit(prompt_size):
    client = FakeClient(parsed=Answer(value="ok"))
    make_llm(client, max_output=10_000_000).parse("sys", "x" * prompt_size, Answer)
    assert worst_case_cost(client.calls[0]) <= 0.5


def test_output_limit_shrinks_as_the_prompt_grows():
    client = FakeClient(parsed=Answer(value="ok"))
    llm = make_llm(client, max_output=10_000_000)
    llm.parse("sys", "x", Answer)
    llm.parse("sys", "x" * 2_000_000, Answer)
    assert client.calls[1]["max_completion_tokens"] < client.calls[0]["max_completion_tokens"]


def test_oversized_prompt_is_refused_before_sending():
    client = FakeClient(parsed=Answer(value="ok"))
    with pytest.raises(CostLimitExceeded):
        make_llm(client).parse("sys", "x" * 3_000_000, Answer)
    assert client.calls == []


def test_model_without_a_known_price_is_refused():
    with pytest.raises(CostLimitExceeded):
        GuardedLLM(FakeClient(), "some-other-model", max_cost_usd=0.5)


def test_settings_reject_a_limit_above_fifty_cents():
    with pytest.raises(ValueError):
        Settings(_env_file=None, max_cost_per_call_usd=0.51)


def test_cost_is_tracked_from_usage():
    llm = make_llm(FakeClient(parsed=Answer(value="ok")))
    llm.parse("sys", "user", Answer)
    assert llm.total_cost_usd == pytest.approx(0.95)


def test_cut_off_answer_raises():
    with pytest.raises(LLMResponseError):
        make_llm(FakeClient(finish_reason="length")).parse("sys", "user", Answer)


def test_refusal_raises():
    with pytest.raises(LLMResponseError):
        make_llm(FakeClient(refusal="no")).parse("sys", "user", Answer)
