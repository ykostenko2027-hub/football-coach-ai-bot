import time
import uuid
from datetime import datetime, timezone
from app.models import (
    AppError,
    CoachRequest,
    CoachResponse,
    HealthResponse,
    RequestRecord,
)
from app.orchestration import CoachOrchestrator
from app.settings import Settings
from app.storage import BaseStorage
from app.telemetry import TelemetryLogger


class CoachService:
    def __init__(
        self,
        settings: Settings,
        orchestrator: CoachOrchestrator,
        storage: BaseStorage,
        telemetry: TelemetryLogger,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.storage = storage
        self.telemetry = telemetry

    def handle_ask(
        self,
        req: CoachRequest,
        request_id: str | None = None,
    ) -> CoachResponse:
        rid = request_id or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        self.telemetry.log(
            rid,
            "service",
            "handle_ask_start",
            text_length=len(req.user_text),
        )
        try:
            output, result, blocked, guard_msg = self.orchestrator.run(
                request_id=rid,
                user_text=req.user_text,
                case_id=req.case_id,
            )
        except AppError as err:
            latency_ms = int((time.perf_counter() - started) * 1000)
            self.storage.save_record(
                RequestRecord(
                    request_id=rid,
                    user_text=req.user_text,
                    status="error",
                    provider=self.settings.llm_provider,
                    model=self.settings.llm_model,
                    latency_ms=latency_ms,
                    error_kind=err.kind,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.telemetry.log(
                rid,
                "service",
                "handle_ask_error",
                error_kind=err.kind,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)

        if blocked:
            self.storage.save_record(
                RequestRecord(
                    request_id=rid,
                    user_text=req.user_text,
                    status="blocked",
                    provider=self.settings.llm_provider,
                    model="guardrail",
                    latency_ms=latency_ms,
                    result_json=None,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            self.telemetry.log(
                rid,
                "service",
                "handle_ask_blocked",
                latency_ms=latency_ms,
            )
            return CoachResponse(
                request_id=rid,
                status="blocked",
                blocked_by_guardrail=True,
                system_message=guard_msg,
                provider=self.settings.llm_provider,
                model="guardrail",
                latency_ms=latency_ms,
            )

        self.storage.save_record(
            RequestRecord(
                request_id=rid,
                user_text=req.user_text,
                status="ok",
                provider=self.settings.llm_provider,
                model=result.model,
                latency_ms=latency_ms,
                result_json=output.model_dump_json() if output else None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        self.telemetry.log(
            rid,
            "service",
            "handle_ask_complete",
            mode=output.mode if output else "unknown",
            latency_ms=latency_ms,
        )
        return CoachResponse(
            request_id=rid,
            status="ok",
            output=output,
            provider=self.settings.llm_provider,
            model=result.model,
            latency_ms=latency_ms,
        )

    def get_health(self, uptime_s: int) -> HealthResponse:
        storage_ok = self.storage.ping()
        mode_str = "mock" if self.settings.llm_provider in ("mock", "recorded") else "real"
        return HealthResponse(
            status="ok" if storage_ok else "degraded",
            version=self.settings.app_version,
            provider=self.settings.llm_provider,
            model=self.settings.llm_model,
            mode=mode_str,
            storage="ok" if storage_ok else "error",
            extra={"ifab_index": "not_loaded"},
            uptime_s=uptime_s,
        )

    def get_history(self, limit: int = 20) -> list[RequestRecord]:
        return self.storage.list_records(limit=limit)
