from pathlib import Path
from app.budget import BudgetTracker
from app.models import AppError, ProviderRequest, ProviderResult
from app.providers.base import BaseProvider
from app.providers.mock import MockProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.recorded import RecordedProvider
from app.settings import Settings
from app.telemetry import TelemetryLogger


class LLMGateway:
    def __init__(self, settings: Settings, telemetry: TelemetryLogger) -> None:
        self.settings = settings
        self.telemetry = telemetry
        self.budget = BudgetTracker(
            limit_usd=settings.budget_daily_usd,
            storage_file=str(Path(settings.db_path).parent / "budget.json"),
        )
        self.provider = self._build_provider(settings)

    def _build_provider(self, settings: Settings) -> BaseProvider:
        if settings.llm_provider == "mock":
            return MockProvider(
                delay_ms=settings.mock_delay_ms,
                failure_rate=settings.mock_failure_rate,
                failure_kind=settings.mock_failure_kind,
            )
        if settings.llm_provider in ("gemini", "openai_compat"):
            return OpenAICompatProvider(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                default_model=settings.llm_model,
            )
        if settings.llm_provider == "recorded":
            real = None
            if settings.record_mode in ("record", "passthrough"):
                real = (
                    OpenAICompatProvider(
                        base_url=settings.llm_base_url,
                        api_key=settings.llm_api_key,
                        default_model=settings.llm_model,
                    )
                    if settings.llm_api_key
                    else MockProvider()
                )
            return RecordedProvider(
                recordings_dir=settings.recordings_dir,
                mode=settings.record_mode,
                real_provider=real,
            )
        raise AppError("unknown_provider", f"Unknown provider {settings.llm_provider}", False, 500)

    def call(self, request: ProviderRequest) -> ProviderResult:
        self.budget.check_budget()
        self.telemetry.log(
            request.request_id,
            "gateway",
            "provider_call_start",
            provider=self.settings.llm_provider,
            model=request.model,
        )
        try:
            result = self.provider.generate(request)
        except AppError as err:
            self.telemetry.log(
                request.request_id,
                "gateway",
                "provider_call_error",
                error_kind=err.kind,
                retryable=err.retryable,
            )
            raise

        if result.cost_usd > 0:
            self.budget.record_cost(result.cost_usd)

        self.telemetry.log(
            request.request_id,
            "gateway",
            "provider_call_success",
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        )
        return result
