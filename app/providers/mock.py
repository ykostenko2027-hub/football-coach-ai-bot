import json
import random
import re
import time
from app.models import (
    AppError,
    CoachStructuredOutput,
    DrillItem,
    MotivationSpeech,
    ProviderRequest,
    ProviderResult,
    RuleExplanation,
    WarmupCooldownBlock,
    WorkoutPlan,
)
from app.providers.base import BaseProvider


class MockProvider(BaseProvider):
    def __init__(
        self,
        delay_ms: int = 0,
        failure_rate: float = 0.0,
        failure_kind: str = "unavailable",
    ) -> None:
        self.delay_ms = delay_ms
        self.failure_rate = failure_rate
        self.failure_kind = failure_kind

    def _maybe_fail(self, model: str) -> ProviderResult | None:
        if self.failure_rate <= 0:
            return None
        if self.failure_rate < 1.0 and random.random() >= self.failure_rate:
            return None
        if self.failure_kind == "timeout":
            raise AppError("timeout", "Mock provider timed out", True, 504)
        if self.failure_kind == "rate_limit":
            raise AppError("rate_limit", "Mock provider rate limit exceeded", True, 429)
        if self.failure_kind == "mid_stream":
            raise AppError("mid_stream_error", "Mock stream interrupted", True, 503)
        if self.failure_kind == "invalid_json":
            return ProviderResult(
                text="{invalid_json_output",
                model=model,
                input_tokens=40,
                output_tokens=10,
                cost_usd=0.0,
            )
        raise AppError("provider_unavailable", "Mock provider unavailable", True, 503)

    def _extract_minutes(self, text: str) -> int:
        match = re.search(r"(\d+)\s*(?:хв|минут|мин)", text.lower())
        if not match:
            return 15
        val = int(match.group(1))
        return max(5, min(val, 90))

    def _build_output(self, request: ProviderRequest) -> CoachStructuredOutput:
        text_lower = request.user_text.lower()
        if request.case_id == "n02" or any(
            k in text_lower for k in ("офсайд", "правил", "рукою", "пенальт", "фол")
        ):
            return CoachStructuredOutput(
                mode="rule_explanation",
                rule_explanation=RuleExplanation(
                    topic="Офсайд (Положення «поза грою»)",
                    official_ifab_rule="Правило 11 IFAB: гравець перебуває в положенні поза грою, якщо будь-яка частина його голови, тулуба або ніг ближча до лінії воріт суперника, ніж м'яч і передостанній гравець захисту.",
                    simple_analogy="Уяви чергу на касу: ти не маєш права пролізти перед передостаннім захисником, поки партнер не віддасть тобі пас. У момент передачі ти маєш бути на лінії з ним або позаду.",
                    verdict_on_user_situation=f"Запит опрацьовано: {request.user_text[:80]}",
                ),
            )
        if request.case_id == "n03" or any(
            k in text_lower for k in ("мотив", "настрой", "налаштуй", "клопп", "гвардіол")
        ):
            persona = "Пеп Гвардіола" if "гвардіол" in text_lower else "Юрген Клопп"
            return CoachStructuredOutput(
                mode="motivation",
                motivation=MotivationSpeech(
                    coach_persona=persona,
                    speech="Слухай уважно! Сьогодні не важливо, хто стоїть навпроти. Виходь на поле з гарячим серцем і холодною головою. Помилився? Пресингуй одразу, забирай м'яч і грай у свій найкращий футбол!",
                    focus_slogan="Дисципліна, сміливість і перший дотик вирішують гру!",
                ),
            )
        if not any(k in text_lower for k in ("хв", "м'яч", "мяч", "трен", "стін", "вправ")):
            return CoachStructuredOutput(
                mode="chat",
                answer="Гарне питання! Тренуйся регулярно, працюй над слабкою ногою і дивись матчі, звертаючи увагу на рух без м'яча.",
            )
        total = self._extract_minutes(request.user_text)
        warmup_m = 1 if total <= 6 else 2
        cooldown_m = 1 if total <= 6 else 2
        work_m = max(2, total - warmup_m - cooldown_m)
        if total <= 6:
            drills = [
                DrillItem(
                    order=1,
                    name="Швидке жонглювання та контроль підйомом",
                    duration_minutes=work_m,
                    reps_or_intensity="Без пауз",
                    technique_tip="Тримай м'яч нижче колін та працюй обома ногами.",
                )
            ]
        else:
            d1 = work_m // 2
            d2 = work_m - d1
            drills = [
                DrillItem(
                    order=1,
                    name="Пас у стіну та м'який перший дотик",
                    duration_minutes=d1,
                    reps_or_intensity="30 повторень",
                    technique_tip="Амортизуй м'яч підошвою або внутрішньою частиною стопи.",
                ),
                DrillItem(
                    order=2,
                    name="Передачі в один дотик слабкою ногою",
                    duration_minutes=d2,
                    reps_or_intensity="40 повторень",
                    technique_tip="Фіксуй гомілкостоп і тримай корпус над м'ячем.",
                ),
            ]
        skill = "Контроль м'яча"
        if "дотик" in text_lower:
            skill = "Перший дотик та передача"
        elif "контрол" in text_lower or "дриблінг" in text_lower:
            skill = "Контроль м'яча на швидкості"
        return CoachStructuredOutput(
            mode="training",
            workout_plan=WorkoutPlan(
                title=f"Експрес-тренування ({total} хв)",
                total_minutes=total,
                target_skill=skill,
                equipment_needed=["М'яч"],
                warmup=WarmupCooldownBlock(
                    name="Суглобова розминка",
                    duration_minutes=warmup_m,
                    description="Оберти гомілкостопами, колінами та легкі перекати м'яча.",
                ),
                drills=drills,
                cooldown=WarmupCooldownBlock(
                    name="Відновлення дихання та розтяжка",
                    duration_minutes=cooldown_m,
                    description="Спокійна статика литок і стегон без ривків.",
                ),
                safety_note="Уважно стеж за покриттям під ногами та уникай різких рухів без розминки.",
            ),
        )

    def generate(self, request: ProviderRequest) -> ProviderResult:
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)
        failed = self._maybe_fail(request.model)
        if failed is not None:
            return failed
        output = self._build_output(request)
        payload = json.dumps(output.model_dump(), ensure_ascii=False)
        return ProviderResult(
            text=payload,
            model=request.model,
            input_tokens=max(10, len(request.user_text) // 3),
            output_tokens=max(20, len(payload) // 4),
            cost_usd=0.0,
        )
