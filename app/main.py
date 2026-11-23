import time
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from app.gateway import LLMGateway
from app.models import (
    AppError,
    CoachRequest,
    CoachResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    RequestRecord,
)
from app.orchestration import CoachOrchestrator
from app.service import CoachService
from app.settings import Settings, load_settings
from app.storage import BaseStorage, SQLiteStorage
from app.telemetry import TelemetryLogger

UI_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Футбольний тренер — Чат</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; height: 100vh; display: flex; flex-direction: column; }
  header { background: #1e293b; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; }
  header h1 { font-size: 17px; font-weight: 600; }
  .badge { padding: 4px 10px; border-radius: 999px; font-size: 12px; background: #065f46; color: #a7f3d0; }
  .badge.err { background: #991b1b; color: #fecaca; }
  #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .msg { max-width: 80%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.5; word-wrap: break-word; }
  .msg.user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 2px; }
  .msg.bot { align-self: flex-start; background: #1e293b; color: #f1f5f9; border-bottom-left-radius: 2px; border: 1px solid #334155; }
  .msg.bot .title { font-weight: 700; color: #38bdf8; margin-bottom: 6px; }
  .msg.bot .sec { margin-top: 8px; font-size: 13px; }
  .msg.bot .badge-time { display: inline-block; background: #334155; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-bottom: 6px; }
  .msg.bot.blocked { border-color: #ef4444; background: #450a0a; color: #fca5a5; }
  .meta { font-size: 10px; color: #94a3b8; margin-top: 6px; text-align: right; }
  footer { background: #1e293b; padding: 14px 20px; border-top: 1px solid #334155; display: flex; gap: 10px; }
  input[type="text"] { flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #f8fafc; font-size: 14px; outline: none; }
  input[type="text"]:focus { border-color: #38bdf8; }
  button { padding: 12px 22px; border-radius: 8px; border: 0; background: #2563eb; color: #fff; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
</head>
<body>
  <header>
    <h1>⚽ Карманний футбольний тренер</h1>
    <span id="health" class="badge">підключення...</span>
  </header>
  <div id="chat">
    <div class="msg bot">
      <div class="title">Привіт! Я твій футбольний тренер та експерт ⚽</div>
      <div>Напиши, що хочеш потренувати (наприклад: <em>«Маю м'яч, стіну і 15 хвилин»</em>), запитай правило (наприклад: <em>«Що таке офсайд?»</em>) або попроси налаштування на матч.</div>
    </div>
  </div>
  <footer>
    <input type="text" id="inp" placeholder="Напишіть повідомлення тренеру..." autocomplete="off">
    <button id="send">Надіслати</button>
  </footer>
<script>
async function loadHealth() {
  const el = document.getElementById('health');
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    el.textContent = `${d.status.toUpperCase()} | ${d.provider} (${d.model})`;
  } catch (e) {
    el.className = 'badge err';
    el.textContent = 'offline';
  }
}

function formatBotResponse(d) {
  if (d.blocked_by_guardrail) {
    return `<div class="title">🛑 Застереження безпеки</div><div>${d.system_message}</div>`;
  }
  const out = d.output;
  if (!out) return `<div>${d.system_message || 'Відповідь відсутня'}</div>`;
  if (out.missing_info) return `<div class="title">❓ Уточни, будь ласка</div><div>${out.missing_info}</div>`;
  if (out.mode === 'chat' && out.answer) return `<div>${out.answer}</div>`;

  if (out.mode === 'training' && out.workout_plan) {
    const p = out.workout_plan;
    let h = `<div class="title">📋 ${p.title}</div>`;
    h += `<div class="badge-time">⏱ ${p.total_minutes} хв | Ціль: ${p.target_skill}</div>`;
    h += `<div class="sec"><strong>1. Розминка (${p.warmup.duration_minutes} хв):</strong> ${p.warmup.description}</div>`;
    p.drills.forEach(dr => {
      h += `<div class="sec"><strong>2. Вправа ${dr.order} (${dr.duration_minutes} хв):</strong> ${dr.name}<br><em>💡 ${dr.technique_tip}</em></div>`;
    });
    h += `<div class="sec"><strong>3. Заминка (${p.cooldown.duration_minutes} хв):</strong> ${p.cooldown.description}</div>`;
    h += `<div class="sec" style="color:#f59e0b">⚠️ ${p.safety_note}</div>`;
    return h;
  }
  if (out.mode === 'rule_explanation' && out.rule_explanation) {
    const r = out.rule_explanation;
    return `<div class="title">📖 ${r.topic}</div><div><strong>Офіційне правило:</strong> ${r.official_ifab_rule}</div><div class="sec"><strong>Аналогія:</strong> ${r.simple_analogy}</div>`;
  }
  if (out.mode === 'motivation' && out.motivation) {
    const m = out.motivation;
    return `<div class="title">🔥 Налаштування від ${m.coach_persona}</div><div>${m.speech}</div><div class="sec" style="font-weight:700;color:#38bdf8">«${m.focus_slogan}»</div>`;
  }
  return `<div>${JSON.stringify(out)}</div>`;
}

async function sendMsg() {
  const inp = document.getElementById('inp');
  const btn = document.getElementById('send');
  const chat = document.getElementById('chat');
  const text = inp.value.trim();
  if (!text) return;

  const uDiv = document.createElement('div');
  uDiv.className = 'msg user';
  uDiv.textContent = text;
  chat.appendChild(uDiv);
  inp.value = '';
  btn.disabled = true;
  chat.scrollTop = chat.scrollHeight;

  const bDiv = document.createElement('div');
  bDiv.className = 'msg bot';
  bDiv.textContent = 'Тренер формує відповідь...';
  chat.appendChild(bDiv);
  chat.scrollTop = chat.scrollHeight;

  try {
    const res = await fetch('/api/coach/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_text: text })
    });
    const d = await res.json();
    if (!res.ok) {
      bDiv.className = 'msg bot blocked';
      bDiv.innerHTML = `<div class="title">Помилка (${d.error.kind})</div><div>${d.error.message}</div><div class="meta">request_id: ${d.error.request_id}</div>`;
    } else {
      if (d.blocked_by_guardrail) bDiv.className = 'msg bot blocked';
      bDiv.innerHTML = formatBotResponse(d) + `<div class="meta">${d.provider} | ${d.latency_ms} мс | id: ${d.request_id}</div>`;
    }
  } catch (err) {
    bDiv.className = 'msg bot blocked';
    bDiv.textContent = 'Помилка мережі при зверненні до сервера.';
  } finally {
    btn.disabled = false;
    chat.scrollTop = chat.scrollHeight;
  }
}

document.getElementById('send').onclick = sendMsg;
document.getElementById('inp').onkeydown = (e) => { if (e.key === 'Enter') sendMsg(); };
loadHealth();
</script>
</body>
</html>
"""


def create_app(
    settings: Settings | None = None,
    storage: BaseStorage | None = None,
) -> FastAPI:
    cfg = settings or load_settings()
    telemetry = TelemetryLogger(cfg.log_file)
    db = storage or SQLiteStorage(cfg.db_path)
    gateway = LLMGateway(cfg, telemetry)
    orchestrator = CoachOrchestrator(cfg, gateway, telemetry)
    service = CoachService(cfg, orchestrator, db, telemetry)
    started_at = time.monotonic()

    application = FastAPI(title="Pocket Football Coach API", version=cfg.app_version)
    application.state.service = service
    application.state.telemetry = telemetry

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        return await call_next(request)

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        payload = ErrorResponse(
            error=ErrorDetail(
                kind=exc.kind,
                message=exc.message,
                retryable=exc.retryable,
                request_id=rid,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        telemetry.log(rid, "controller", "validation_error")
        payload = ErrorResponse(
            error=ErrorDetail(
                kind="validation_error",
                message="Invalid request payload",
                retryable=False,
                request_id=rid,
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        telemetry.log(rid, "controller", "unexpected_error", error_type=type(exc).__name__)
        payload = ErrorResponse(
            error=ErrorDetail(
                kind="internal_error",
                message="Unexpected server error",
                retryable=False,
                request_id=rid,
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    @application.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(content=UI_HTML)

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        uptime_s = int(time.monotonic() - started_at)
        return service.get_health(uptime_s=uptime_s)

    @application.post("/api/coach/ask", response_model=CoachResponse)
    async def ask_coach(request: Request, body: CoachRequest) -> CoachResponse:
        rid = request.state.request_id
        telemetry.log(rid, "controller", "ask_received")
        response = service.handle_ask(body, request_id=rid)
        telemetry.log(rid, "controller", "ask_responded", status=response.status)
        return response

    @application.get("/api/history", response_model=list[RequestRecord])
    async def history(limit: int = 20) -> list[RequestRecord]:
        return service.get_history(limit=limit)

    return application


app = create_app()
