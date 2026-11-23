from abc import ABC, abstractmethod
from app.models import ProviderRequest, ProviderResult


class BaseProvider(ABC):
    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResult:
        pass
