from enum import Enum


class TaskStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    CANCELLED = "cancelled"


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class InputSource(str, Enum):
    TELEGRAM = "telegram"
    HTTP = "http"


class InputType(str, Enum):
    VOICE = "voice"
    TEXT = "text"


class IntentType(str, Enum):
    CREATE_REMINDER = "create_reminder"
    LIST_TASKS = "list_tasks"
    COMPLETE_TASK = "complete_task"
    SNOOZE_TASK = "snooze_task"
    CANCEL_TASK = "cancel_task"
    UNKNOWN = "unknown"
