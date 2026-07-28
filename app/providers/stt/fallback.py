import logging
from collections.abc import Sequence

from app.providers.stt.base import BaseTranscriptionProvider, TranscriptionError

logger = logging.getLogger(__name__)

_MAX_ERROR_CHARS = 500


class FallbackTranscriptionProvider(BaseTranscriptionProvider):
    """Try STT providers in order, returning the first non-empty transcript."""

    def __init__(self, providers: Sequence[tuple[str, BaseTranscriptionProvider]]) -> None:
        if not providers:
            raise ValueError("FallbackTranscriptionProvider requires at least one provider")
        self.providers = list(providers)

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        failures: list[str] = []

        for name, provider in self.providers:
            try:
                transcript = await provider.transcribe(audio_bytes, filename)
            except Exception as exc:
                failures.append(f"{name}: {str(exc)[:_MAX_ERROR_CHARS]}")
                logger.warning("STT provider %s failed, trying next provider: %s", name, exc)
                continue

            if transcript.strip():
                return transcript.strip()

            failures.append(f"{name}: returned empty transcript")
            logger.warning("STT provider %s returned empty transcript, trying next provider", name)

        raise TranscriptionError(f"All STT providers failed: {'; '.join(failures)}")
