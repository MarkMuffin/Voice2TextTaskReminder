from abc import ABC, abstractmethod


class BaseTranscriptionProvider(ABC):
    """Abstract STT provider. All providers must implement transcribe()."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        """Transcribe audio bytes to text. Raises TranscriptionError on failure."""
        ...


class TranscriptionError(Exception):
    pass
