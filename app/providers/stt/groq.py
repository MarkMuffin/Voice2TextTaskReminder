from app.providers.stt.openai_compatible import OpenAICompatibleSTTProvider

GROQ_STT_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "whisper-large-v3"


class GroqWhisperProvider(OpenAICompatibleSTTProvider):
    """Groq Whisper STT — uses OpenAI-compatible API at Groq endpoint."""

    def __init__(self, api_key: str, model: str = GROQ_DEFAULT_MODEL) -> None:
        super().__init__(api_key=api_key, model=model, base_url=GROQ_STT_BASE_URL)
