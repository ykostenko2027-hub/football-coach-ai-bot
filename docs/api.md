# API-контракти

## 1. HTTP-маршрути

### `GET /api/health`
Перевірка стану та конфігурації без виклику платної моделі й без розкриття секретів.
* **Відповідь `200 OK`**:
```json
{
  "status": "ok",
  "version": "628fc8a",
  "provider": "mock",
  "model": "gemini-1.5-flash",
  "mode": "mock",
  "storage": "ok",
  "extra": { "ifab_index": "not_loaded" },
  "uptime_s": 12
}
```

### `POST /api/coach/ask`
Синхронний запуск сценарію через усі шари системи.
* **Тіло запиту**:
```json
{
  "user_text": "Маю м'яч, стіну і 15 хвилин, хочу потренувати перший дотик",
  "case_id": null
}
```
* **Відповідь `200 OK`**:
```json
{
  "request_id": "a1b2c3d4e5f6",
  "status": "ok",
  "output": {
    "mode": "training",
    "workout_plan": { "...": "..." },
    "rule_explanation": null,
    "motivation": null
  },
  "system_message": null,
  "blocked_by_guardrail": false,
  "provider": "mock",
  "model": "gemini-1.5-flash",
  "latency_ms": 4
}
```

### `GET /api/history?limit=20`
Повертає список збережених записів запитів зі сховища SQLite (`200 OK`).

---

## 2. Єдиний формат помилки

Використовується для всіх контрольованих помилок (`422`, `429`, `503`, `504`, `500`):
```json
{
  "error": {
    "kind": "provider_unavailable",
    "message": "Mock provider unavailable",
    "retryable": true,
    "request_id": "a1b2c3d4e5f6"
  }
}
```
* **Статуси**: `422` (невалідний вхід), `429` (rate limit / `budget`), `502` (`invalid_output` — модель двічі повернула невалідну структуру, вхід користувача коректний), `503` (провайдер недоступний / немає запису в `replay`), `504` (таймаут), `500` (непередбачений збій).

---

## 3. Контракт провайдера та схема виходу

* **Вхід провайдера (`ProviderRequest`)**: `request_id`, `system_prompt`, `user_text`, `model`, `timeout_s`, `response_schema`, `case_id`.
* **Вихід провайдера (`ProviderResult`)**: `text` (JSON-рядок), `model`, `input_tokens`, `output_tokens`, `cost_usd`.
* **Структурований вихід (`CoachStructuredOutput`)**: `mode` (`training | rule_explanation | motivation | chat`), відповідний блок (`workout_plan`, `rule_explanation`, `motivation` або `answer`) і `missing_info`, якщо даних не вистачає.
