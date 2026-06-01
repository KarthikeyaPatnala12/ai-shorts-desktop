from fastapi import APIRouter

from backend.app.schemas import SubtitleRequest, SubtitleResponse
from backend.app.services.subtitles import generate_subtitles

router = APIRouter()


@router.post("", response_model=SubtitleResponse)
def create_subtitles(payload: SubtitleRequest) -> SubtitleResponse:
    return SubtitleResponse(content=generate_subtitles(payload.segments, payload.format))
