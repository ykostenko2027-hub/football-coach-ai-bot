import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from app.models import AppError, ProviderRequest, ProviderResult
from app.providers.base import BaseProvider


class RecordedProvider(BaseProvider):
    def __init__(
        self,
        recordings_dir: str,
        mode: str = "replay",
        real_provider: BaseProvider | None = None,
    ) -> None:
        self.dir = Path(recordings_dir)
        self.mode = mode
        self.real_provider = real_provider
        self.dir.mkdir(parents=True, exist_ok=True)

    def _hash(self, req: ProviderRequest) -> str:
        key = f"{req.model}|{req.temperature}|{req.max_tokens}|{req.system_prompt}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def generate(self, request: ProviderRequest) -> ProviderResult:
        h = self._hash(request)
        file_path = self.dir / f"{h}.json"

        if self.mode == "replay":
            if not file_path.exists():
                raise AppError(
                    "recording_not_found",
                    f"Recording {h} not found for replay mode",
                    retryable=False,
                    status_code=503,
                )
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return ProviderResult(
                text=data["text"],
                model=data.get("model", request.model),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                cost_usd=data.get("cost_usd", 0.0),
            )

        if self.mode == "record":
            if not self.real_provider:
                raise AppError("configuration_error", "No real provider configured for recording", False, 500)
            res = self.real_provider.generate(request)
            data = {
                "hash": h,
                "request_preview": request.user_text[:60],
                "model": res.model,
                "text": res.text,
                "input_tokens": res.input_tokens,
                "output_tokens": res.output_tokens,
                "cost_usd": res.cost_usd,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return res

        if self.real_provider:
            return self.real_provider.generate(request)
        raise AppError("configuration_error", "No provider available", False, 500)
