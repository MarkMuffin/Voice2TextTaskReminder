from app.providers.stt.base import BaseTranscriptionProvider


class MockTranscriptionProvider(BaseTranscriptionProvider):
    """Returns a fixed transcript. Used in tests."""

    def __init__(self, fixed_text: str = "Напомни мне купить молоко завтра утром") -> None:
        self.fixed_text = fixed_text

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        return self.fixed_text
