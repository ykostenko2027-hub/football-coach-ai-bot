import json
from datetime import datetime, timezone
from pathlib import Path
from app.models import AppError


class BudgetTracker:
    def __init__(self, limit_usd: float, storage_file: str) -> None:
        self.limit_usd = limit_usd
        self.storage_path = Path(storage_file)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def get_spent(self) -> float:
        if not self.storage_path.exists():
            return 0.0
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return 0.0
        if data.get("date") != self._today():
            return 0.0
        return float(data.get("spent_usd", 0.0))

    def record_cost(self, cost_usd: float) -> None:
        if cost_usd <= 0:
            return
        total = round(self.get_spent() + cost_usd, 6)
        self.storage_path.write_text(
            json.dumps({"date": self._today(), "spent_usd": total}), encoding="utf-8"
        )

    def check_budget(self) -> None:
        spent = self.get_spent()
        if spent >= self.limit_usd:
            raise AppError(
                kind="budget",
                message=f"Daily budget exceeded: ${spent:.4f} of ${self.limit_usd:.2f}",
                retryable=False,
                status_code=429,
            )
