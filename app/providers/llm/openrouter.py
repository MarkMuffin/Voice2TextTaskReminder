import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
import pytz

from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser

logger = logging.getLogger(__name__)

_MAX_LOG_CHARS = 1000

_SYSTEM_PROMPT = """\
You are a personal task assistant that parses voice commands in Russian and English.
Extract structured information and return ONLY a valid JSON object matching the schema below.

CRITICAL OUTPUT RULES:
- Return ONLY the raw JSON object. Nothing else.
- No markdown, no code blocks (no ```), no explanation, no prose.
- No trailing commas. All string values must be properly quoted.
- All fields listed in the schema must be present in the output.

{temporal_context}

Natural language time rules:
- "утром" / "morning" = 09:00
- "днём" / "после обеда" / "afternoon" = 14:00
- "вечером" / "evening" = 19:00
- "после работы" / "after work" = 18:30
- "ночью" / "night" = 22:00
- If date is mentioned but no time → use 09:00
- If completely unclear datetime → set requires_confirmation=true

Relative date rules (use ONLY Current date above — never rely on model knowledge of today):
- "завтра" / "tomorrow" → Current date + 1 day
- "послезавтра" / "day after tomorrow" → Current date + 2 days
- "в <weekday>" / "on <weekday>" → nearest future occurrence of that weekday \
(if today IS that weekday, use +7 days instead)
- "в следующий <weekday>" / "next <weekday>" → that weekday in the NEXT calendar week
- "на следующей неделе" / "next week" → Monday of next calendar week
- "на выходных" / "this weekend" → nearest upcoming Saturday
- All date arithmetic must be performed in User timezone.

Recurring task rules (use intent "create_recurring_task" when user says \
"every ...", "каждый ...", "каждую ...", "ежедневно", "еженедельно", "раз в ..."):
- recurrence.type: "daily" | "weekly" | "monthly"
- recurrence.interval: how many units between runs (default 1)
- recurrence.time_of_day: "HH:MM" (24h)
- recurrence.day_of_week: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun (only for weekly)
- recurrence.day_of_month: 1-31 (only for monthly)

Required JSON schema — output must be exactly this structure with all fields present:
{{
  "intent": "create_reminder" | "list_tasks" | "complete_task" | "snooze_task" | \
"cancel_task" | "create_recurring_task" | "list_recurring_tasks" | \
"cancel_recurring_task" | "pause_recurring_task" | "resume_recurring_task" | "unknown",
  "title": "string or null",
  "remind_at": "ISO datetime string or null",
  "timezone": "IANA timezone string",
  "confidence": 0.0-1.0,
  "requires_confirmation": true or false,
  "clarification_question": "string or null",
  "snooze_until": "ISO datetime string or null",
  "task_reference": "string or null",
  "recurrence": {{"type": "daily"|"weekly"|"monthly", "interval": 1, \
"time_of_day": "HH:MM", "day_of_week": null, "day_of_month": null}} or null,
  "recurring_task_reference": "string or null"
}}

Example (recurring weekly):
Input: "каждую пятницу в 17 пополнить фонд"
Output: {{"intent":"create_recurring_task","title":"Пополнить фонд","remind_at":null,\
"timezone":"{timezone}","confidence":0.9,"requires_confirmation":false,\
"clarification_question":null,"snooze_until":null,"task_reference":null,\
"recurrence":{{"type":"weekly","interval":1,"time_of_day":"17:00","day_of_week":4,\
"day_of_month":null}},"recurring_task_reference":null}}
"""

_FALLBACK_QUESTION = "Не смог разобрать команду. Можешь повторить?"


def build_llm_temporal_context(now: datetime, timezone: str) -> str:
    """Return the temporal context block injected into the LLM system prompt."""
    return (
        f"Current datetime: {now.isoformat()}\n"
        f"Current date: {now.strftime('%Y-%m-%d')}\n"
        f"Current weekday: {now.strftime('%A')}\n"
        f"User timezone: {timezone}"
    )


def _safe_fallback() -> ParsedIntent:
    return ParsedIntent(
        intent=IntentType.UNKNOWN,
        confidence=0.0,
        requires_confirmation=True,
        clarification_question=_FALLBACK_QUESTION,
    )


def _extract_json(raw: str) -> Any:
    """
    Try to extract a valid JSON object from raw LLM output.

    Strategies (in order):
      1. Direct json.loads
      2. Extract from markdown ```json ... ``` block
      3. Extract first { ... last } substring
    """
    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: markdown code block  ``` or ```json
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { … last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON object found in LLM response")


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
        now = datetime.now(tz)
        temporal_context = build_llm_temporal_context(now, timezone)
        system = _SYSTEM_PROMPT.format(temporal_context=temporal_context, timezone=timezone)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
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
                if response.status_code == 400:
                    # Model doesn't support response_format — retry without it
                    logger.warning(
                        "OpenRouter: response_format rejected (model=%s, HTTP 400), retrying without it",
                        self.model,
                    )
                    payload_retry = {k: v for k, v in payload.items() if k != "response_format"}
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload_retry,
                    )
            response.raise_for_status()

            raw_content: str | None = (
                response.json().get("choices", [{}])[0].get("message", {}).get("content")
            )

            # Guard: None or empty content
            if not raw_content or not raw_content.strip():
                logger.warning("OpenRouter returned empty/null content for model=%s", self.model)
                return _safe_fallback()

            content = raw_content.strip()
            logger.debug(
                "OpenRouter raw response (model=%s, len=%d): %s",
                self.model,
                len(content),
                content[:_MAX_LOG_CHARS],
            )

            data = _extract_json(content)
            return ParsedIntent(**data)

        except Exception as exc:
            # Log without leaking the API key or full payload
            logger.warning(
                "OpenRouter parse failed (model=%s): %s",
                self.model,
                str(exc)[:_MAX_LOG_CHARS],
            )
            return _safe_fallback()
