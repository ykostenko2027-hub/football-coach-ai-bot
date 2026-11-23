# Кишеньковий футбольний тренер та експерт (Pocket Football Coach)

AI-асистент для футболістів-аматорів: генерація персональних тренувань під наявний інвентар, розбір правил IFAB та налаштування на гру.

---

## 📂 Структура проєкту

* [`app/`](app/) — серверна частина (FastAPI): контролер, сервіс, оркестрація, шлюз, провайдери (`mock` / заготовка реального), SQLite-сховище, телеметрія.
* [`tests/`](tests/) — автотести каркаса (`pytest`).
* [`docs/passport.md`](docs/passport.md) — паспорт проєкту.
* [`docs/architecture.md`](docs/architecture.md), [`docs/api.md`](docs/api.md), [`docs/adr.md`](docs/adr.md) — архітектура, контракти й рішення (ADR).
* [`docs/backlog.md`](docs/backlog.md) — план розробки (ПР14–ПР20).
* [`eval/cases.json`](eval/cases.json) — набір прикладів для оцінювання.

---

## 🚀 Запуск з чистого клону

1. Скопіюйте шаблон налаштувань (за замовчуванням увімкнено `LLM_PROVIDER=mock`, ключ не потрібен):
   ```powershell
   copy .env.example .env
   ```
2. Встановіть залежності:
   ```powershell
   pip install -r requirements.txt
   ```
3. Запустіть сервер:
   ```powershell
   uvicorn app.main:app --reload
   ```
4. Відкрийте у браузері: `http://127.0.0.1:8000` (або перевірте `http://127.0.0.1:8000/api/health`).

---

## 🧪 Запуск тестів

```powershell
python -m pytest -v
```

Тести не ходять у мережу. Живий тест: `$env:LIVE_TESTS="1"; python -m pytest -k live`.

---

## 🔌 Режими провайдера (`.env`)

| `LLM_PROVIDER` | Що відбувається |
| :-- | :-- |
| `mock` | Заготовлені відповіді, без ключа й мережі. |
| `gemini` | Справжня модель, потрібен `LLM_API_KEY`. |
| `recorded` | Відповіді з `tests/recordings/coach/` (`RECORD_MODE=replay`) або запис нових (`record`). |

## 📊 Прогін набору прикладів

```powershell
python -m eval.run --k 3
```
Результат — `eval/runs/<мітка>.json` зі зведенням за видами.
