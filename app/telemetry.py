import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TelemetryLogger:
    def __init__(self, log_file: str) -> None:
        self.log_path = Path(log_file)
        if self.log_path.parent:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        request_id: str,
        layer: str,
        event: str,
        **fields: Any,
    ) -> None:
        safe_fields = {
            k: v
            for k, v in fields.items()
            if "key" not in k.lower() and "secret" not in k.lower() and "token" not in k.lower() or k.endswith("_tokens")
        }
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "layer": layer,
            "event": event,
            **safe_fields,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
