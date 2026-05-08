from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import InputSource, IntentType, ReminderStatus, TaskStatus

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
