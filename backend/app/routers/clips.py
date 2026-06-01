from fastapi import APIRouter

from backend.app.schemas import ClipDetectionRequest, ClipDetectionResponse
from backend.app.services.clip_detection import detect_clips

router = APIRouter()


@router.post("/detect", response_model=ClipDetectionResponse)
def detect_clip_candidates(payload: ClipDetectionRequest) -> ClipDetectionResponse:
    return ClipDetectionResponse(
        clips=detect_clips(payload.segments, payload.target_duration_seconds)
    )
