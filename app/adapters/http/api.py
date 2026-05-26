import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.domain.enums import InputSource
from app.domain.schemas import CaptureResponse, CaptureTextRequest, RecurringTaskCreate

if TYPE_CHECKING:
    from app.container import Container

from app.services.recurring_service import RecurringTaskService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capture", tags=["capture"])
recurring_router = APIRouter(prefix="/recurring-tasks", tags=["recurring-tasks"])

# Container injected via FastAPI app state
_container: "Container | None" = None


def get_container() -> "Container":
    if _container is None:
        raise RuntimeError("Container not initialized")
    return _container


def set_container(c: "Container") -> None:
    global _container
    _container = c


@router.post("/text", response_model=CaptureResponse)
async def capture_text(
    body: CaptureTextRequest,
    container: "Container" = Depends(get_container),
) -> CaptureResponse:
    try:
        intent = await container.capture_service.process_text(
            user_id=body.user_id,
            text=body.text,
            source=body.source,
            timezone=body.timezone,
        )
        result = await container.action_router.route(
            user_id=body.user_id,
            intent=intent,
            raw_text=body.text,
        )

        if result.requires_confirmation:
            return CaptureResponse(
                success=False,
                message=result.clarification_question or "Требуется уточнение",
                intent=str(intent.intent),
                requires_confirmation=True,
                clarification_question=result.clarification_question,
            )

        task_id = result.task.id if result.task else None
        return CaptureResponse(
            success=result.success,
            message="OK",
            task_id=task_id,
            intent=str(intent.intent),
        )
    except Exception as exc:
        logger.exception("capture/text error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/audio", response_model=CaptureResponse)
async def capture_audio(
    user_id: str = Form(...),
    timezone: str = Form(default="Europe/Amsterdam"),
    audio: UploadFile = File(...),
    container: "Container" = Depends(get_container),
) -> CaptureResponse:
    try:
        audio_bytes = await audio.read()
        transcript, intent = await container.capture_service.process_voice(
            user_id=user_id,
            audio_bytes=audio_bytes,
            source=InputSource.HTTP,
            timezone=timezone,
            filename=audio.filename or "audio.ogg",
        )
        result = await container.action_router.route(
            user_id=user_id, intent=intent, raw_text=transcript
        )

        if result.requires_confirmation:
            return CaptureResponse(
                success=False,
                message=result.clarification_question or "Требуется уточнение",
                intent=str(intent.intent),
                requires_confirmation=True,
                clarification_question=result.clarification_question,
            )

        task_id = result.task.id if result.task else None
        return CaptureResponse(
            success=result.success,
            message="OK",
            task_id=task_id,
            intent=str(intent.intent),
        )
    except Exception as exc:
        logger.exception("capture/audio error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _get_recurring_service(container: "Container") -> RecurringTaskService:
    if container.recurring_service is None:
        raise HTTPException(status_code=503, detail="Recurring tasks are disabled")
    return container.recurring_service


# NOTE: These endpoints rely on user_id supplied by the caller for ownership checks.
# There is no token-based authentication — they are intended for internal/trusted use
# (e.g. same-host services or a future authenticated gateway). Do not expose publicly
# without adding an auth layer.


@recurring_router.post("", status_code=201)
async def create_recurring_task(
    body: RecurringTaskCreate,
    container: "Container" = Depends(get_container),
) -> dict:
    svc = _get_recurring_service(container)
    try:
        rule = await svc.create_recurring_task(body)
        return {"id": rule.id, "title": rule.title, "status": rule.status}
    except Exception as exc:
        logger.exception("recurring-tasks POST error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@recurring_router.get("")
async def list_recurring_tasks(
    user_id: str,
    container: "Container" = Depends(get_container),
) -> list[dict]:
    svc = _get_recurring_service(container)
    try:
        rules = await svc.list_all_visible(user_id)
        return [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "recurrence_type": r.recurrence_type,
                "interval": r.interval,
                "time_of_day": r.time_of_day,
                "day_of_week": r.day_of_week,
                "day_of_month": r.day_of_month,
                "next_run_at": r.next_run_at.isoformat() if r.next_run_at else None,
            }
            for r in rules
        ]
    except Exception as exc:
        logger.exception("recurring-tasks GET error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@recurring_router.post("/{rule_id}/cancel")
async def cancel_recurring_task(
    rule_id: int,
    user_id: str,
    container: "Container" = Depends(get_container),
) -> dict:
    svc = _get_recurring_service(container)
    from app.domain.enums import CompleteTaskResult

    result, rule = await svc.cancel_recurring(user_id, rule_id)
    if result == CompleteTaskResult.FORBIDDEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if result == CompleteTaskResult.NOT_FOUND:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": rule_id, "status": "cancelled"}


@recurring_router.post("/{rule_id}/pause")
async def pause_recurring_task(
    rule_id: int,
    user_id: str,
    container: "Container" = Depends(get_container),
) -> dict:
    svc = _get_recurring_service(container)
    from app.domain.enums import CompleteTaskResult

    result, rule = await svc.pause_recurring(user_id, rule_id)
    if result == CompleteTaskResult.FORBIDDEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if result == CompleteTaskResult.NOT_FOUND:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": rule_id, "status": "paused"}


@recurring_router.post("/{rule_id}/resume")
async def resume_recurring_task(
    rule_id: int,
    user_id: str,
    container: "Container" = Depends(get_container),
) -> dict:
    svc = _get_recurring_service(container)
    from app.domain.enums import CompleteTaskResult

    result, rule = await svc.resume_recurring(user_id, rule_id)
    if result == CompleteTaskResult.FORBIDDEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if result == CompleteTaskResult.NOT_FOUND:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": rule_id, "status": "active"}
