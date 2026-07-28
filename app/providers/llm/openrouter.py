from app.providers.llm.openai_compatible import (
    OpenAICompatibleIntentParser,
    _extract_json,
    _safe_fallback,
    build_llm_temporal_context,
)

OPENROUTER_LLM_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"


class OpenRouterIntentParser(OpenAICompatibleIntentParser):
    def __init__(
        self,
        api_key: str,
        model: str = OPENROUTER_DEFAULT_MODEL,
        base_url: str = OPENROUTER_LLM_BASE_URL,
        *,
        raise_on_failure: bool = False,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_name="OpenRouter",
            raise_on_failure=raise_on_failure,
            http_referer="https://github.com/voice2text-task-reminder",
        )


__all__ = [
    "OpenRouterIntentParser",
    "_extract_json",
    "_safe_fallback",
    "build_llm_temporal_context",
]
