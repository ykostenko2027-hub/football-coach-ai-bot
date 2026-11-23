import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from app.gateway import LLMGateway
from app.models import AppError
from app.orchestration import PROMPT_VERSION, CoachOrchestrator
from app.settings import load_settings
from app.telemetry import TelemetryLogger


def get_path(data, path: str):
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def check(rule: dict, data: dict) -> bool:
    v = get_path(data, rule["path"])
    kind, exp = rule["check"], rule.get("value")
    if kind == "exists":
        return v is not None
    if v is None:
        return False
    if kind == "equals":
        return v == exp
    if kind == "contains_ignore_case":
        return str(exp).lower() in str(v).lower()
    if kind == "not_contains":
        return str(exp).lower() not in str(v).lower()
    if kind == "min_length":
        return len(v) >= exp
    if kind == "max_length":
        return len(v) <= exp
    raise ValueError(f"unknown check {kind}")


def run_case(orch: CoachOrchestrator, case: dict) -> dict:
    started = time.perf_counter()
    try:
        out, res, blocked, msg = orch.run("eval", case["input"]["user_text"], case["id"])
        data = {**(out.model_dump() if out else {}), "blocked_by_guardrail": blocked, "system_message": msg}
        tokens = res.input_tokens + res.output_tokens
        error = None
    except AppError as e:
        data, tokens, error = {}, 0, e.kind
    failed = [r for r in case["expect"] if not check(r, data)]
    return {
        "passed": not failed and error is None,
        "error": error,
        "failed_checks": failed,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "tokens": tokens,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="eval/cases.json")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--label", default=None)
    args = p.parse_args()

    s = load_settings()
    tel = TelemetryLogger(s.log_file)
    orch = CoachOrchestrator(s, LLMGateway(s, tel), tel)
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    label = args.label or f"{PROMPT_VERSION}-{s.llm_provider}-{s.llm_model}-{datetime.now(timezone.utc):%Y%m%d}"

    results, summary = [], defaultdict(lambda: {"runs": 0, "passed": 0})
    for case in cases:
        for attempt in range(args.k):
            r = run_case(orch, case)
            results.append({"id": case["id"], "kind": case["kind"], "attempt": attempt + 1, **r})
            summary[case["kind"]]["runs"] += 1
            summary[case["kind"]]["passed"] += int(r["passed"])

    total = sum(v["passed"] for v in summary.values())
    runs = sum(v["runs"] for v in summary.values())
    report = {
        "label": label,
        "provider": s.llm_provider,
        "model": s.llm_model,
        "prompt_version": PROMPT_VERSION,
        "date": datetime.now(timezone.utc).isoformat(),
        "pass_rate": round(total / runs, 3) if runs else 0,
        "summary_by_kind": summary,
        "results": results,
    }
    out = Path("eval/runs") / f"{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{label}: {total}/{runs} passed")
    for kind, v in summary.items():
        print(f"  {kind}: {v['passed']}/{v['runs']}")
    for r in results:
        if not r["passed"]:
            print(f"  FAIL {r['id']}#{r['attempt']}: {r['error'] or r['failed_checks']}")


if __name__ == "__main__":
    main()
