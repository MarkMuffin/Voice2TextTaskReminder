from datetime import datetime, timedelta

import pytz

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser


class MockIntentParser(BaseIntentParser):
    """
    Returns a deterministic ParsedIntent for testing.
    Can be configured with a fixed response or use simple keyword matching.
    """

    def __init__(self, fixed_response: ParsedIntent | None = None) -> None:
        self._fixed = fixed_response

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        if self._fixed is not None:
            return self._fixed

        return self._keyword_parse(text, timezone)

    @staticmethod
    def _keyword_parse(text: str, timezone: str) -> ParsedIntent:
        lower = text.lower()
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)

        if any(w in lower for w in ["список", "задачи", "покажи"]):
            return ParsedIntent(intent=IntentType.LIST_TASKS, confidence=0.9)

        if any(w in lower for w in ["готово", "выполнил", "сделал", "выполнено"]):
            return ParsedIntent(
                intent=IntentType.COMPLETE_TASK,
                task_reference=text,
                confidence=0.85,
            )

        if any(w in lower for w in ["отмени", "отменить", "удали"]):
            return ParsedIntent(
                intent=IntentType.CANCEL_TASK,
                task_reference=text,
                confidence=0.85,
            )

        if any(w in lower for w in ["позже", "перенеси", "снуз"]):
            snooze_until = (now + timedelta(hours=1)).isoformat()
            return ParsedIntent(
                intent=IntentType.SNOOZE_TASK,
                task_reference=text,
                snooze_until=snooze_until,
                confidence=0.8,
            )

        # Default: create_reminder
        tomorrow_morning = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        title = text.strip().rstrip(".")
        if len(title) > 80:
            title = title[:80]

        return ParsedIntent(
            intent=IntentType.CREATE_REMINDER,
            title=title,
            remind_at=tomorrow_morning.isoformat(),
            timezone=timezone,
            confidence=0.75,
            requires_confirmation=False,
        )
