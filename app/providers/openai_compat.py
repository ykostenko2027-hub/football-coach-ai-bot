import json
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from app.models import AppError, ProviderRequest, ProviderResult
from app.providers.base import BaseProvider


class OpenAICompatProvider(BaseProvider):
    def __init__(self, base_url: str, api_key: str, default_model: str) -> None:
        self.default_model = default_model
        self.client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)

    def _calc_cost(self, model: str, in_tokens: int, out_tokens: int) -> float:
        in_rate = 0.075 / 1_000_000
        out_rate = 0.30 / 1_000_000
        return round((in_tokens * in_rate) + (out_tokens * out_rate), 6)

    def generate(self, request: ProviderRequest) -> ProviderResult:
        model = request.model or self.default_model
        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_text},
        ]
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout_s,
        }
        if request.response_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "coach_structured_output",
                    "schema": request.response_schema,
                    "strict": False,
                },
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = self.client.chat.completions.create(**kwargs)
        except APITimeoutError as e:
            raise AppError("timeout", "Model request timed out", True, 504) from e
        except RateLimitError as e:
            raise AppError("rate_limit", "Model rate limit exceeded", True, 429) from e
        except (APIConnectionError, InternalServerError) as e:
            raise AppError("unavailable", "Model provider unavailable", True, 503) from e
        except AuthenticationError as e:
            raise AppError("auth", "Authentication failed with provider", False, 401) from e
        except BadRequestError as e:
            raise AppError("bad_request", f"Bad request to model: {str(e)[:150]}", False, 400) from e
        except Exception as e:
            raise AppError("provider_error", f"Provider error: {str(e)[:150]}", False, 500) from e

        choice = resp.choices[0]
        content = choice.message.content or "{}"
        in_tokens = resp.usage.prompt_tokens if resp.usage else 0
        out_tokens = resp.usage.completion_tokens if resp.usage else 0
        cost = self._calc_cost(model, in_tokens, out_tokens)

        return ProviderResult(
            text=content,
            model=model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=cost,
        )
