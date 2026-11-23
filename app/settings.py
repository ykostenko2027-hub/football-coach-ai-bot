import os
import subprocess
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator


def _detect_version() -> str:
    env_ver = os.getenv("APP_VERSION", "").strip()
    if env_ver:
        return env_ver
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return res.stdout.strip() or "dev"
    except Exception:
        return "dev"


class Settings(BaseModel):
    llm_provider: Literal["mock", "recorded", "gemini", "openai_compat"] = "mock"
    llm_model: str = Field(default="gemini-1.5-flash", min_length=1)
    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_timeout_s: float = Field(default=10.0, gt=0)
    mock_delay_ms: int = Field(default=0, ge=0)
    mock_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    mock_failure_kind: Literal[
        "timeout", "rate_limit", "unavailable", "invalid_json", "mid_stream"
    ] = "unavailable"
    record_mode: Literal["replay", "record", "passthrough"] = "replay"
    recordings_dir: str = "tests/recordings/coach"
    budget_daily_usd: float = Field(default=1.0, gt=0)
    db_path: str = Field(default="data/coach.db", min_length=1)
    log_file: str = Field(default="logs/app.log", min_length=1)
    app_version: str = "dev"

    @model_validator(mode="after")
    def check_provider_key(self) -> "Settings":
        if self.llm_provider in ("gemini", "openai_compat") and not self.llm_api_key.strip():
            raise ValueError(
                f"LLM_API_KEY is required when LLM_PROVIDER='{self.llm_provider}'"
            )
        return self


def load_settings() -> Settings:
    load_dotenv(override=False)
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "mock").strip().lower(),
        llm_model=os.getenv("LLM_MODEL", "gemini-1.5-flash").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv(
            "LLM_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ).strip(),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "10.0")),
        mock_delay_ms=int(os.getenv("MOCK_DELAY_MS", "0")),
        mock_failure_rate=float(os.getenv("MOCK_FAILURE_RATE", "0.0")),
        mock_failure_kind=os.getenv("MOCK_FAILURE_KIND", "unavailable").strip().lower(),
        record_mode=os.getenv("RECORD_MODE", "replay").strip().lower(),
        recordings_dir=os.getenv("RECORDINGS_DIR", "tests/recordings/coach").strip(),
        budget_daily_usd=float(os.getenv("BUDGET_DAILY_USD", "1.0")),
        db_path=os.getenv("DB_PATH", "data/coach.db").strip(),
        log_file=os.getenv("LOG_FILE", "logs/app.log").strip(),
        app_version=_detect_version(),
    )
