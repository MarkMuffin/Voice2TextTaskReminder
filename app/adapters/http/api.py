import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.domain.enums import InputSource
from app.domain.schemas import CaptureResponse, CaptureTextRequest

if TYPE_CHECKING:
    from app.container import Container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capture", tags=["capture"])

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
        raise HTTPException(status_code=500, detail=str(exc))


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
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
