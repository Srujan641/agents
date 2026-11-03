import pytest
from pydantic import ValidationError

from meeting_agent.config import Settings


def test_defaults_run_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_api_key is None
    assert settings.use_mock_integrations is True


def test_api_key_is_hidden_when_printed():
    settings = Settings(_env_file=None, openai_api_key="sk-secret")
    assert "sk-secret" not in repr(settings)


def test_rejects_zero_poll_interval():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, poll_interval_seconds=0)
