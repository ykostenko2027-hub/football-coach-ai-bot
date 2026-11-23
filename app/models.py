from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        retryable: bool = False,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class CoachRequest(BaseModel):
    user_text: str = Field(..., min_length=10, max_length=500)
    case_id: str | None = None

    @field_validator("user_text")
    @classmethod
    def strip_and_validate(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 10:
            raise ValueError("user_text must contain at least 10 non-space characters")
        return cleaned


class WarmupCooldownBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    duration_minutes: int = Field(..., ge=1)
    description: str


class DrillItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: int = Field(..., ge=1)
    name: str
    duration_minutes: int = Field(..., ge=1)
    reps_or_intensity: str
    technique_tip: str


class WorkoutPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    total_minutes: int = Field(..., ge=1, le=90)
    target_skill: str
    equipment_needed: list[str]
    warmup: WarmupCooldownBlock
    drills: list[DrillItem] = Field(..., min_length=1)
    cooldown: WarmupCooldownBlock
    safety_note: str


class RuleExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str
    official_ifab_rule: str
    simple_analogy: str
    verdict_on_user_situation: str


class MotivationSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coach_persona: str
    speech: str
    focus_slogan: str


class CoachStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["training", "rule_explanation", "motivation", "chat"]
    workout_plan: WorkoutPlan | None = None
    rule_explanation: RuleExplanation | None = None
    motivation: MotivationSpeech | None = None
    answer: str | None = None
    missing_info: str | None = None


class CoachResponse(BaseModel):
    request_id: str
    status: Literal["ok", "blocked"]
    output: CoachStructuredOutput | None = None
    system_message: str | None = None
    blocked_by_guardrail: bool = False
    provider: str
    model: str
    latency_ms: int


class ErrorDetail(BaseModel):
    kind: str
    message: str
    retryable: bool
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ProviderRequest(BaseModel):
    request_id: str
    system_prompt: str
    user_text: str
    model: str
    timeout_s: float
    temperature: float = 0.2
    max_tokens: int = 1024
    response_schema: dict[str, Any] | None = None
    case_id: str | None = None


class ProviderResult(BaseModel):
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class RequestRecord(BaseModel):
    request_id: str
    user_text: str
    status: str
    provider: str
    model: str
    latency_ms: int
    result_json: str | None = None
    error_kind: str | None = None
    created_at: str


class HealthResponse(BaseModel):
    status: str
    version: str
    provider: str
    model: str
    mode: str
    storage: str
    extra: dict[str, str]
    uptime_s: int
