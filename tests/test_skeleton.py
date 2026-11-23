import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.gateway import LLMGateway
from app.main import create_app
from app.models import CoachRequest, ErrorResponse
from app.orchestration import CoachOrchestrator
from app.service import CoachService
from app.settings import Settings
from app.storage import SQLiteStorage
from app.telemetry import TelemetryLogger


def _make_settings(tmp_path: Path, **overrides) -> Settings:
    data = {
        "llm_provider": "mock",
        "llm_model": "gemini-1.5-flash",
        "llm_api_key": "",
        "db_path": str(tmp_path / "test.db"),
        "log_file": str(tmp_path / "test.log"),
        "app_version": "test",
    }
    data.update(overrides)
    return Settings(**data)


def test_health_and_no_secrets(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    client = TestClient(create_app(settings=settings))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"
    assert body["mode"] == "mock"
    assert body["storage"] == "ok"
    assert body["extra"]["ifab_index"] == "not_loaded"
    assert "api_key" not in json.dumps(body).lower()


def test_api_ask_through_layers_and_logs(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    app = create_app(settings=settings)
    client = TestClient(app)

    resp = client.post(
        "/api/coach/ask",
        json={"user_text": "Маю м'яч, стіну і 15 хвилин, хочу потренувати перший дотик"},
    )
    assert resp.status_code == 200
    data = resp.json()
    rid = data["request_id"]
    assert data["status"] == "ok"
    assert data["output"]["mode"] == "training"
    assert data["output"]["workout_plan"]["total_minutes"] == 15

    log_lines = [
        json.loads(line)
        for line in Path(settings.log_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    layers = {entry["layer"] for entry in log_lines if entry["request_id"] == rid}
    assert {"controller", "service", "orchestration", "gateway"}.issubset(layers)

    hist = client.get("/api/history")
    assert hist.status_code == 200
    assert hist.json()[0]["request_id"] == rid


def test_service_direct_without_http(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    telemetry = TelemetryLogger(settings.log_file)
    storage = SQLiteStorage(settings.db_path)
    gateway = LLMGateway(settings, telemetry)
    orchestrator = CoachOrchestrator(settings, gateway, telemetry)
    service = CoachService(settings, orchestrator, storage, telemetry)

    res = service.handle_ask(
        CoachRequest(user_text="Поясни що таке офсайд у футболі простими словами")
    )
    assert res.status == "ok"
    assert res.output is not None
    assert res.output.mode == "rule_explanation"
    assert storage.get_record(res.request_id) is not None


@pytest.mark.parametrize(
    "failure_kind,expected_status,expected_err_kind",
    [
        ("unavailable", 503, "provider_unavailable"),
        ("timeout", 504, "timeout"),
        ("rate_limit", 429, "rate_limit"),
        ("invalid_json", 502, "invalid_output"),
    ],
)
def test_provider_failure_returns_controlled_error(
    tmp_path: Path,
    failure_kind: str,
    expected_status: int,
    expected_err_kind: str,
) -> None:
    settings = _make_settings(
        tmp_path,
        mock_failure_rate=1.0,
        mock_failure_kind=failure_kind,
    )
    client = TestClient(create_app(settings=settings))

    resp = client.post(
        "/api/coach/ask",
        json={"user_text": "Маю м'яч, стіну і 15 хвилин на техніку пасу"},
    )
    assert resp.status_code == expected_status
    err = ErrorResponse.model_validate(resp.json())
    assert err.error.kind == expected_err_kind
    assert len(err.error.request_id) > 0


def test_settings_fail_fast_without_api_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        _make_settings(tmp_path, llm_provider="gemini", llm_api_key="")
