from app.providers.llm.openai_compatible import OpenAICompatibleIntentParser

GROQ_LLM_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"


class GroqIntentParser(OpenAICompatibleIntentParser):
    def __init__(
        self,
        api_key: str,
        model: str = GROQ_DEFAULT_MODEL,
        base_url: str = GROQ_LLM_BASE_URL,
        *,
        raise_on_failure: bool = False,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_name="Groq",
            raise_on_failure=raise_on_failure,
        )
