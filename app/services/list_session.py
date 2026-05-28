from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

SESSION_TTL = timedelta(hours=24)


@dataclass
class _ListSession:
    visible_task_ids: list[int]
    completed_task_ids: list[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ListSessionStore:
    """In-memory store for interactive /list session state.

    Keyed by (chat_id, message_id). Lost on restart — acceptable per spec.
    """

    def __init__(self, ttl: timedelta = SESSION_TTL) -> None:
        self._sessions: dict[tuple[int, int], _ListSession] = {}
        self._ttl = ttl

    def create_session(self, chat_id: int, message_id: int, visible_task_ids: list[int]) -> None:
        self._cleanup_expired()
        self._sessions[(chat_id, message_id)] = _ListSession(
            visible_task_ids=list(visible_task_ids)
        )

    def mark_completed(self, chat_id: int, message_id: int, task_id: int) -> None:
        session = self._sessions.get((chat_id, message_id))
        if session is None:
            return
        if task_id not in session.visible_task_ids:
            return
        if task_id not in session.completed_task_ids:
            session.completed_task_ids.append(task_id)

    def get_completed_ids(self, chat_id: int, message_id: int) -> list[int]:
        session = self._sessions.get((chat_id, message_id))
        return list(session.completed_task_ids) if session else []

    def get_visible_task_ids(self, chat_id: int, message_id: int) -> list[int]:
        session = self._sessions.get((chat_id, message_id))
        return list(session.visible_task_ids) if session else []

    def clear_session(self, chat_id: int, message_id: int) -> None:
        self._sessions.pop((chat_id, message_id), None)

    def _cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [k for k, v in self._sessions.items() if now - v.created_at >= self._ttl]
        for k in expired:
            del self._sessions[k]
