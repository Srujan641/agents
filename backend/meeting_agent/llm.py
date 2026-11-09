import json
import logging
import math
import threading
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MIN_OUTPUT_TOKENS = 1000
# Covers message framing and the strict-mode rewrite of the schema.
_REQUEST_OVERHEAD_BYTES = 500


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


# The guard charges the long-context rate (prompts over 272K tokens) on every call, so its
# ceiling holds at any prompt size. Check these against OpenAI's pricing page if it changes.
_PRICES = {"gpt-6-luna": ModelPrice(input_per_million=0.20, output_per_million=0.75)}


class CostLimitExceeded(Exception):
    """The call could cost more than the limit, so it was not sent."""


class LLMResponseError(Exception):
    """The model returned no usable answer."""


class GuardedLLM:
    """Refuses to send any request whose worst-case cost is above the limit."""

    def __init__(
        self, client: Any, model: str, max_cost_usd: float, max_output_tokens: int = 16000
    ) -> None:
        if model not in _PRICES:
            raise CostLimitExceeded(f"No price on file for {model}, so its cost can't be capped")
        self._client = client
        self._model = model
        self._price = _PRICES[model]
        self._max_cost = max_cost_usd
        self._max_output_tokens = max_output_tokens
        self.total_cost_usd = 0.0
        self.max_call_cost_usd = 0.0
        self._lock = threading.Lock()

    def parse[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        max_output = self._output_budget(system, user, schema)
        response = self._client.chat.completions.parse(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            max_completion_tokens=max_output,
        )
        cost = self._record_cost(response.usage)
        with self._lock:
            self.total_cost_usd += cost
            self.max_call_cost_usd = max(self.max_call_cost_usd, cost)

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMResponseError(f"Answer cut off at the {max_output} token limit")
        if choice.message.parsed is None:
            raise LLMResponseError(f"No parsed answer: {choice.message.refusal or 'empty'}")
        return choice.message.parsed

    def _output_budget(self, system: str, user: str, schema: type[BaseModel]) -> int:
        # A token is at least one byte in practice, so bytes over-count the prompt.
        input_tokens = (
            len(system.encode())
            + len(user.encode())
            + len(json.dumps(schema.model_json_schema()).encode())
            + _REQUEST_OVERHEAD_BYTES
        )
        remaining = self._max_cost - input_tokens * self._price.input_per_million / 1_000_000
        affordable = math.floor(remaining * 1_000_000 / self._price.output_per_million)
        if affordable < _MIN_OUTPUT_TOKENS:
            raise CostLimitExceeded(
                f"A prompt of up to {input_tokens} tokens can't fit under ${self._max_cost}"
            )
        return min(affordable, self._max_output_tokens)

    def _record_cost(self, usage: Any) -> float:
        cost = (
            usage.prompt_tokens * self._price.input_per_million
            + usage.completion_tokens * self._price.output_per_million
        ) / 1_000_000
        logger.info(
            "LLM call: %d in, %d out, at most $%.4f",
            usage.prompt_tokens,
            usage.completion_tokens,
            cost,
        )
        return cost
