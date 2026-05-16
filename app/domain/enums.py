from enum import StrEnum


class TaskStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class InputSource(StrEnum):
    TELEGRAM = "telegram"
    HTTP = "http"


class InputType(StrEnum):
    VOICE = "voice"
    TEXT = "text"


class IntentType(StrEnum):
    CREATE_REMINDER = "create_reminder"
    LIST_TASKS = "list_tasks"
    COMPLETE_TASK = "complete_task"
    SNOOZE_TASK = "snooze_task"
    CANCEL_TASK = "cancel_task"
    UNKNOWN = "unknown"


class CompleteTaskResult(StrEnum):
    COMPLETED = "completed"
    ALREADY_INACTIVE = "already_inactive"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
