"""Unit tests for ListSessionStore."""

from datetime import timedelta

from app.services.list_session import ListSessionStore


def test_create_and_get_visible_ids():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20, 30])
    assert store.get_visible_task_ids(1, 100) == [10, 20, 30]


def test_mark_completed_stores_id():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20, 30])
    store.mark_completed(1, 100, 20)
    assert store.get_completed_ids(1, 100) == [20]


def test_mark_completed_multiple_preserves_order():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20, 30])
    store.mark_completed(1, 100, 20)
    store.mark_completed(1, 100, 30)
    assert store.get_completed_ids(1, 100) == [20, 30]


def test_mark_completed_deduplicates():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20, 30])
    store.mark_completed(1, 100, 20)
    store.mark_completed(1, 100, 20)
    assert store.get_completed_ids(1, 100) == [20]


def test_completed_ids_scoped_by_message():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20])
    store.create_session(1, 200, [30, 40])
    store.mark_completed(1, 100, 10)
    store.mark_completed(1, 200, 30)
    assert store.get_completed_ids(1, 100) == [10]
    assert store.get_completed_ids(1, 200) == [30]


def test_completed_ids_scoped_by_chat():
    store = ListSessionStore()
    store.create_session(1, 100, [10])
    store.create_session(2, 100, [20])
    store.mark_completed(1, 100, 10)
    assert store.get_completed_ids(2, 100) == []


def test_clear_session_removes_state():
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20])
    store.mark_completed(1, 100, 10)
    store.clear_session(1, 100)
    assert store.get_completed_ids(1, 100) == []
    assert store.get_visible_task_ids(1, 100) == []


def test_missing_session_returns_empty():
    store = ListSessionStore()
    assert store.get_completed_ids(1, 999) == []
    assert store.get_visible_task_ids(1, 999) == []


def test_mark_completed_no_session_is_noop():
    store = ListSessionStore()
    store.mark_completed(1, 999, 10)  # should not raise
    assert store.get_completed_ids(1, 999) == []


def test_create_session_overwrites_existing():
    """New /list call creates fresh session, discarding previous state."""
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20])
    store.mark_completed(1, 100, 10)
    store.create_session(1, 100, [30, 40])
    assert store.get_completed_ids(1, 100) == []
    assert store.get_visible_task_ids(1, 100) == [30, 40]


def test_ttl_cleanup():
    store = ListSessionStore(ttl=timedelta(seconds=0))
    store.create_session(1, 100, [10])
    # Next create_session triggers _cleanup_expired; TTL=0 means already expired
    store.create_session(1, 200, [20])
    assert store.get_visible_task_ids(1, 100) == []
    assert store.get_visible_task_ids(1, 200) == [20]


def test_visible_ids_are_independent_copy():
    """Modifying the input list does not affect stored session."""
    store = ListSessionStore()
    ids = [1, 2, 3]
    store.create_session(1, 100, ids)
    ids.append(4)
    assert store.get_visible_task_ids(1, 100) == [1, 2, 3]


def test_get_completed_ids_returns_independent_copy():
    """Modifying returned list does not affect stored session."""
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20])
    store.mark_completed(1, 100, 10)
    result = store.get_completed_ids(1, 100)
    result.append(20)
    assert store.get_completed_ids(1, 100) == [10]


def test_mark_completed_ignores_task_not_in_visible_ids():
    """task_id not in visible_task_ids must not be added to session state."""
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20])
    store.mark_completed(1, 100, 99)  # 99 was not in the visible list
    assert store.get_completed_ids(1, 100) == []


def test_mark_completed_only_visible_ids_are_tracked():
    """Only tasks that were visible can be tracked as completed."""
    store = ListSessionStore()
    store.create_session(1, 100, [10, 20, 30])
    store.mark_completed(1, 100, 20)  # visible
    store.mark_completed(1, 100, 99)  # not visible
    assert store.get_completed_ids(1, 100) == [20]
