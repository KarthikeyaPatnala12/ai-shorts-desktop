from fastapi import APIRouter

from backend.app.schemas import TranscriptionRequest, TranscriptionResponse
from backend.app.services.transcription import transcribe_video

router = APIRouter()


@router.post("", response_model=TranscriptionResponse)
def create_transcription(payload: TranscriptionRequest) -> TranscriptionResponse:
    return transcribe_video(payload.video_path, language=payload.language, task=payload.task)
