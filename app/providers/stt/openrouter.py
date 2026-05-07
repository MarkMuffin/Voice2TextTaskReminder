import base64
import io

import httpx

from app.providers.stt.base import BaseTranscriptionProvider, TranscriptionError

OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"

# OGG is not in their documented list; convert to format they support
_FORMAT_MAP = {
    "ogg": "wav",  # will re-label, actual bytes don't change for Whisper
    "mp3": "mp3",
    "wav": "wav",
    "flac": "flac",
    "mp4": "mp4",
    "webm": "webm",
}


class OpenRouterSTTProvider(BaseTranscriptionProvider):
    """
    STT via OpenRouter /api/v1/audio/transcriptions.
    Uses JSON + base64 audio (not multipart like standard OpenAI).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/whisper-large-v3-turbo",
        language: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
        fmt = _FORMAT_MAP.get(ext, "wav")

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        payload: dict = {
            "model": self.model,
            "input_audio": {
                "data": audio_b64,
                "format": fmt,
            },
        }
        if self.language:
            payload["language"] = self.language

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(OPENROUTER_STT_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise TranscriptionError(
                f"OpenRouter STT error {response.status_code}: {response.text}"
            )

        data = response.json()
        # Response: {"text": "...", ...}
        text = data.get("text") or data.get("transcript") or ""
        return text.strip()
