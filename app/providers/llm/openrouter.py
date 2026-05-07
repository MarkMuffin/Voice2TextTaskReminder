import json
import logging
from datetime import datetime

import httpx
import pytz

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a personal task assistant that parses voice commands in Russian and English.
Extract structured information and return ONLY valid JSON matching the schema below.

Current datetime (ISO): {now}
User timezone: {timezone}

Natural language time rules:
- "утром" / "morning" = 09:00
- "днём" / "после обеда" / "afternoon" = 14:00
- "вечером" / "evening" = 19:00
- "после работы" / "after work" = 18:30
- "ночью" / "night" = 22:00
- If date is mentioned but no time → use 09:00
- If completely unclear datetime → set requires_confirmation=true

Schema:
{{
  "intent": "create_reminder" | "list_tasks" | "complete_task" | "snooze_task" | "cancel_task" | "unknown",
  "title": "string or null",
  "remind_at": "ISO datetime string or null",
  "timezone": "IANA timezone string",
  "confidence": 0.0-1.0,
  "requires_confirmation": true/false,
  "clarification_question": "string or null",
  "snooze_until": "ISO datetime string or null",
  "task_reference": "string or null"
}}

Return ONLY the JSON object, no explanation, no markdown.
"""


class OpenRouterIntentParser(BaseIntentParser):
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o-mini",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        tz = pytz.timezone(timezone)
        now_str = datetime.now(tz).isoformat()
        system = _SYSTEM_PROMPT.format(now=now_str, timezone=timezone)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/voice2text-task-reminder",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown code block if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            return ParsedIntent(**data)
        except Exception as exc:
            logger.warning("OpenRouter parse failed: %s", exc)
            return ParsedIntent(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                requires_confirmation=True,
                clarification_question="Не удалось разобрать команду. Попробуй ещё раз.",
            )
