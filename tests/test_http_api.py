import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.http.api import router as capture_router, set_container
from app.domain.enums import IntentType
from app.domain.schemas import ParsedIntent
from app.providers.llm.mock import MockIntentParser
from fastapi import FastAPI


def make_app(container):
    app = FastAPI()
    app.include_router(capture_router)
    set_container(container)
    return app


@pytest.fixture
def app(container):
    return make_app(container)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    response = await client.get("/capture/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_capture_text_create_reminder(client, container):
    # Use mock LLM that returns create_reminder
    container.capture_service._llm = MockIntentParser(
        fixed_response=ParsedIntent(
            intent=IntentType.CREATE_REMINDER,
            title="Тест задача",
            remind_at="2025-06-01T09:00:00+00:00",
            timezone="UTC",
            confidence=0.9,
        )
    )
    response = await client.post(
        "/capture/text",
        json={"user_id": "user1", "text": "Напомни тест задача завтра"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["task_id"] is not None


async def test_capture_text_list_tasks(client, container):
    container.capture_service._llm = MockIntentParser(
        fixed_response=ParsedIntent(intent=IntentType.LIST_TASKS, confidence=1.0)
    )
    response = await client.post(
        "/capture/text",
        json={"user_id": "user2", "text": "покажи задачи"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "IntentType.LIST_TASKS"


async def test_capture_text_requires_confirmation(client, container):
    container.capture_service._llm = MockIntentParser(
        fixed_response=ParsedIntent(
            intent=IntentType.CREATE_REMINDER,
            title=None,
            confidence=0.4,
            requires_confirmation=True,
            clarification_question="О чём напомнить?",
        )
    )
    response = await client.post(
        "/capture/text",
        json={"user_id": "user3", "text": "напомни"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["requires_confirmation"] is True


async def test_capture_text_unknown_user_id(client, container):
    response = await client.post(
        "/capture/text",
        json={"user_id": "", "text": "test"},
    )
    # Empty user_id still processes (no validation at API level for user_id)
    assert response.status_code in (200, 422)


async def test_capture_audio(client, container):
    container.capture_service._llm = MockIntentParser(
        fixed_response=ParsedIntent(
            intent=IntentType.CREATE_REMINDER,
            title="Audio task",
            remind_at="2025-06-01T09:00:00+00:00",
            timezone="UTC",
            confidence=0.9,
        )
    )
    fake_audio = b"fake audio bytes"
    response = await client.post(
        "/capture/audio",
        data={"user_id": "user4", "timezone": "UTC"},
        files={"audio": ("test.ogg", fake_audio, "audio/ogg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
