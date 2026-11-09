from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Optional here so stages that don't call them can run without credentials.
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    # le=0.5 makes this a hard ceiling: a higher value in .env refuses to start.
    max_cost_per_call_usd: float = Field(default=0.5, gt=0, le=0.5)
    max_output_tokens: int = Field(default=16000, ge=1000)
    drive_folder_id: str | None = None
    google_service_account_file: Path = Path("credentials.json")

    poll_interval_seconds: int = Field(default=60, ge=1)
    # Wait this long after a file changes, so half-written files aren't picked up.
    settle_seconds: int = Field(default=60, ge=0)
    stale_after_seconds: int = Field(default=1800, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    database_path: Path = Path("database/meeting_agent.db")
    use_mock_integrations: bool = True
