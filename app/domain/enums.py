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
    CREATE_RECURRING_TASK = "create_recurring_task"
    LIST_RECURRING_TASKS = "list_recurring_tasks"
    CANCEL_RECURRING_TASK = "cancel_recurring_task"
    PAUSE_RECURRING_TASK = "pause_recurring_task"
    RESUME_RECURRING_TASK = "resume_recurring_task"


class CompleteTaskResult(StrEnum):
    COMPLETED = "completed"
    ALREADY_INACTIVE = "already_inactive"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"


class RecurringTaskStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class RecurrenceType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
