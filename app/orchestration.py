import re
from pathlib import Path
from app.gateway import LLMGateway
from app.models import (
    AppError,
    CoachStructuredOutput,
    ProviderRequest,
    ProviderResult,
)
from app.settings import Settings
from app.telemetry import TelemetryLogger

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "coach"
PROMPT_VERSION = "v1"
USER_TEXT_BUDGET_CHARS = 500
INJURY_WORDS = ("болить", "біль", "травм", "хруст", "потягнув", "перелом")
INJECTION_WORDS = ("забудь усі", "ignore previous", "системний промпт", "jailbreak", "термінал")
INJURY_MESSAGE = "Здоров'я понад усе! При болю чи травмі тренування заборонені. Звернися до лікаря."
INJECTION_MESSAGE = "Я футбольний тренер і відповідаю лише на питання про футбол, тренування та правила."


def load_prompt(version: str = PROMPT_VERSION) -> tuple[dict[str, str], str]:
    content = (PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")
    _, header, body = content.split("---", 2)
    meta = {}
    for line in header.strip().splitlines():
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"')
    return meta, body.strip()


def render_prompt(body: str, user_text: str) -> str:
    safe = user_text.replace("<<<", "").replace(">>>", "")[:USER_TEXT_BUDGET_CHARS].strip()
    return body.replace("{{ user_text }}", safe)


def extract_minutes(text: str) -> int | None:
    t = text.lower()
    m = re.search(r"(\d{1,2})\s*(?:хв|хвилин|мин)", t) or re.search(r"(?:хв|хвилин)\w*\s*(\d{1,2})", t)
    return int(m.group(1)) if m else None


def check_guardrails(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in INJECTION_WORDS):
        return INJECTION_MESSAGE
    if any(w in t for w in INJURY_WORDS):
        return INJURY_MESSAGE
    return None


def validate_output(raw: str, user_text: str) -> CoachStructuredOutput:
    out = CoachStructuredOutput.model_validate_json(raw)
    blocks = {
        "training": out.workout_plan,
        "rule_explanation": out.rule_explanation,
        "motivation": out.motivation,
        "chat": out.answer,
    }
    if blocks[out.mode] is None and not out.missing_info:
        raise ValueError(f"mode '{out.mode}' requires its block or missing_info")
    if out.mode == "training" and out.workout_plan:
        plan = out.workout_plan
        asked = extract_minutes(user_text)
        if asked:
            plan.total_minutes = asked
        fixed = plan.warmup.duration_minutes + plan.cooldown.duration_minutes
        work = plan.total_minutes - fixed
        if work < len(plan.drills):
            raise ValueError("total_minutes too small for warmup, drills and cooldown")
        share, rest = divmod(work, len(plan.drills))
        for i, d in enumerate(plan.drills):
            d.order = i + 1
            d.duration_minutes = share + (1 if i < rest else 0)
    if out.mode == "rule_explanation" and out.rule_explanation:
        if not re.search(r"\d", out.rule_explanation.official_ifab_rule):
            raise ValueError("official_ifab_rule must contain the IFAB law number")
    return out


class CoachOrchestrator:
    def __init__(self, settings: Settings, gateway: LLMGateway, telemetry: TelemetryLogger) -> None:
        self.settings = settings
        self.gateway = gateway
        self.telemetry = telemetry
        self.meta, self.body = load_prompt()

    def _request(self, rid: str, prompt: str, user_text: str, case_id: str | None) -> ProviderRequest:
        return ProviderRequest(
            request_id=rid,
            system_prompt=prompt,
            user_text=user_text,
            model=self.settings.llm_model,
            timeout_s=self.settings.llm_timeout_s,
            temperature=float(self.meta["temperature"]),
            max_tokens=int(self.meta["max_tokens"]),
            response_schema=CoachStructuredOutput.model_json_schema(),
            case_id=case_id,
        )

    def run(
        self, request_id: str, user_text: str, case_id: str | None = None
    ) -> tuple[CoachStructuredOutput | None, ProviderResult, bool, str | None]:
        guard = check_guardrails(user_text)
        if guard:
            self.telemetry.log(request_id, "orchestration", "guardrail_blocked")
            return None, ProviderResult(text="", model="guardrail"), True, guard

        prompt = render_prompt(self.body, user_text)
        self.telemetry.log(
            request_id,
            "orchestration",
            "context_assembled",
            prompt_version=PROMPT_VERSION,
            schema=self.meta["schema"],
            sources={
                "instruction": len(self.body) // 4,
                "user_input": min(len(user_text), USER_TEXT_BUDGET_CHARS) // 4,
                "reserve_output": int(self.meta["max_tokens"]),
            },
        )
        req = self._request(request_id, prompt, user_text, case_id)
        result = self.gateway.call(req)
        try:
            return validate_output(result.text, user_text), result, False, None
        except ValueError as exc:
            self.telemetry.log(
                request_id, "orchestration", "validation_failed", error=str(exc)[:200], raw=result.text[:200]
            )
            error_note = f"\n\nПопередня відповідь невалідна: {str(exc)[:200]}. Поверни валідний JSON."
            retry = self._request(request_id, prompt + error_note, user_text, case_id)
            result = self.gateway.call(retry)
            try:
                return validate_output(result.text, user_text), result, False, None
            except ValueError as exc2:
                self.telemetry.log(
                    request_id, "orchestration", "validation_retry_failed", error=str(exc2)[:200], raw=result.text[:200]
                )
                raise AppError(
                    kind="invalid_output",
                    message="Тренер повернув некоректну відповідь. Спробуй переформулювати запит.",
                    retryable=False,
                    status_code=502,
                ) from exc2
