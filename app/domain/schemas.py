import re
from datetime import datetime

import pytz
from pydantic import BaseModel, Field, field_validator

from app.domain.enums import (
    InputSource,
    IntentType,
    RecurrenceType,
    ReminderStatus,
    TaskStatus,
)

# ─── Recurrence ──────────────────────────────────────────────────────────────


class RecurrenceRule(BaseModel):
    type: RecurrenceType
    interval: int = 1
    time_of_day: str  # "HH:MM"
    day_of_week: int | None = None
    day_of_month: int | None = None

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("interval must be >= 1")
        return v

    @field_validator("time_of_day")
    @classmethod
    def validate_time_of_day(cls, v: str) -> str:
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("time_of_day must be HH:MM")
        h, m = int(v[:2]), int(v[3:])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Invalid time: {v}")
        return v

    @field_validator("day_of_week")
    @classmethod
    def validate_day_of_week(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 6):
            raise ValueError("day_of_week must be 0 (Mon) – 6 (Sun)")
        return v

    @field_validator("day_of_month")
    @classmethod
    def validate_day_of_month(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 31):
            raise ValueError("day_of_month must be 1–31")
        return v


class RecurringTaskCreate(BaseModel):
    user_id: str
    title: str
    raw_text: str | None = None
    source: InputSource = InputSource.TELEGRAM
    timezone: str = "Europe/Amsterdam"
    recurrence: RecurrenceRule

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


# ─── LLM parsed intent ──────────────────────────────────────────────────────


class ParsedIntent(BaseModel):
    intent: IntentType
    title: str | None = None
    remind_at: str | None = None  # ISO datetime string
    timezone: str = "Europe/Amsterdam"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_confirmation: bool = False
    clarification_question: str | None = None
    snooze_until: str | None = None  # ISO datetime string
    task_reference: str | None = None  # fuzzy title reference for complete/cancel/snooze
    recurrence: RecurrenceRule | None = None
    recurring_task_reference: str | None = None


# ─── Task ────────────────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    user_id: str
    title: str
    raw_text: str | None = None
    source: InputSource = InputSource.TELEGRAM
    remind_at: datetime | None = None
    timezone: str = "Europe/Amsterdam"


class TaskRead(BaseModel):
    id: int
    user_id: str
    title: str
    raw_text: str | None
    source: str
    status: TaskStatus
    remind_at: datetime | None
    timezone: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    remind_at: datetime | None = None
    completed_at: datetime | None = None


# ─── Reminder ────────────────────────────────────────────────────────────────


class ReminderRead(BaseModel):
    id: int
    task_id: int
    remind_at: datetime
    status: ReminderStatus
    sent_at: datetime | None

    model_config = {"from_attributes": True}


# ─── CaptureLog ──────────────────────────────────────────────────────────────


class CaptureLogRead(BaseModel):
    id: int
    user_id: str
    source: str
    input_type: str
    raw_text: str | None
    transcript: str | None
    parsed_intent: dict | None
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── HTTP Capture API ────────────────────────────────────────────────────────


class CaptureTextRequest(BaseModel):
    user_id: str
    text: str
    source: InputSource = InputSource.HTTP
    timezone: str = "Europe/Amsterdam"


class CaptureAudioRequest(BaseModel):
    user_id: str
    source: InputSource = InputSource.HTTP
    timezone: str = "Europe/Amsterdam"


class CaptureResponse(BaseModel):
    success: bool
    message: str
    task_id: int | None = None
    intent: str | None = None
    requires_confirmation: bool = False
    clarification_question: str | None = None
