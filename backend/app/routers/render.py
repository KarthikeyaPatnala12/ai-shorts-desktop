from fastapi import APIRouter

from backend.app.schemas import RenderRequest, RenderResponse
from backend.app.services.rendering import build_render_command

router = APIRouter()


@router.post("", response_model=RenderResponse)
def render_clip(payload: RenderRequest) -> RenderResponse:
    command = build_render_command(
        video_path=payload.video_path,
        start_seconds=payload.start_seconds,
        end_seconds=payload.end_seconds,
        subtitle_path=payload.subtitle_path,
        output_path=payload.output_path,
    )
    return RenderResponse(output_path=payload.output_path, command=command)
