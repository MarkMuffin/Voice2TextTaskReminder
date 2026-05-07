import io

import httpx

from app.providers.stt.base import BaseTranscriptionProvider, TranscriptionError


class OpenAICompatibleSTTProvider(BaseTranscriptionProvider):
    """
    STT provider using OpenAI-compatible /audio/transcriptions endpoint.
    Works with OpenAI Whisper API and any compatible service.
    """

    def __init__(self, api_key: str, model: str = "whisper-1", base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (filename, io.BytesIO(audio_bytes), "audio/ogg")}
            data = {"model": self.model, "response_format": "text"}
            response = await client.post(url, headers=headers, files=files, data=data)

        if response.status_code != 200:
            raise TranscriptionError(
                f"STT API error {response.status_code}: {response.text}"
            )
        return response.text.strip()
