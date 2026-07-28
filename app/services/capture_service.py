import logging

from app.domain.enums import InputSource, InputType
from app.domain.models import CaptureLog
from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser
from app.providers.stt.base import BaseTranscriptionProvider
from app.services.direct_reminder_parser import DirectReminderParser
from app.storage.repositories import CaptureLogRepository

logger = logging.getLogger(__name__)


class CaptureService:
    def __init__(
        self,
        stt: BaseTranscriptionProvider,
        llm: BaseIntentParser,
        log_repo: CaptureLogRepository,
        direct_reminder_parser: DirectReminderParser | None = None,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._log_repo = log_repo
        self._direct_reminder_parser = direct_reminder_parser or DirectReminderParser()

    async def process_voice(
        self,
        user_id: str,
        audio_bytes: bytes,
        source: InputSource = InputSource.TELEGRAM,
        timezone: str = "Europe/Amsterdam",
        filename: str = "audio.ogg",
    ) -> tuple[str, ParsedIntent]:
        """Transcribe audio, parse intent, log everything. Returns (transcript, intent)."""
        transcript = await self._stt.transcribe(audio_bytes, filename)
        logger.info("Transcribed for %s: %r", user_id, transcript)

        intent = await self._parse_intent(transcript, timezone)
        logger.info("Intent for %s: %s (conf=%.2f)", user_id, intent.intent, intent.confidence)

        await self._log_repo.create(
            CaptureLog(
                user_id=user_id,
                source=source,
                input_type=InputType.VOICE,
                transcript=transcript,
                parsed_intent=intent.model_dump(),
                confidence=intent.confidence,
            )
        )
        return transcript, intent

    async def process_text(
        self,
        user_id: str,
        text: str,
        source: InputSource = InputSource.TELEGRAM,
        timezone: str = "Europe/Amsterdam",
    ) -> ParsedIntent:
        """Parse plain text intent, log it. Returns intent."""
        intent = await self._parse_intent(text, timezone)
        logger.info("Intent for %s: %s (conf=%.2f)", user_id, intent.intent, intent.confidence)

        await self._log_repo.create(
            CaptureLog(
                user_id=user_id,
                source=source,
                input_type=InputType.TEXT,
                raw_text=text,
                parsed_intent=intent.model_dump(),
                confidence=intent.confidence,
            )
        )
        return intent

    async def _parse_intent(self, text: str, timezone: str) -> ParsedIntent:
        direct_intent = self._direct_reminder_parser.parse(text, timezone)
        if direct_intent is not None:
            logger.info("Direct reminder parser matched (title=%r)", direct_intent.title)
            return direct_intent
        return await self._llm.parse(text, timezone)
