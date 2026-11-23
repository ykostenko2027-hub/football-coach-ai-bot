from app.models import AppError, ProviderRequest, ProviderResult
from app.providers.base import BaseProvider


class NotImplementedProvider(BaseProvider):
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def generate(self, request: ProviderRequest) -> ProviderResult:
        raise AppError(
            kind="provider_not_implemented",
            message=f"Provider '{self.provider_name}' will be connected in PR15",
            retryable=False,
            status_code=503,
        )
