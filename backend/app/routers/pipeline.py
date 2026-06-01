from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.schemas import ProcessVideoRequest, ProcessVideoResponse, VideoSummary
from backend.app.services.media import MediaProcessingError
from backend.app.services.pipeline import process_video

router = APIRouter()


@router.get("/videos", response_model=list[VideoSummary])
def list_videos(db: Session = Depends(get_db)) -> list[VideoSummary]:
    videos = db.query(models.Video).order_by(desc(models.Video.created_at)).limit(25).all()
    return [
        VideoSummary(
            id=video.id,
            title=video.title,
            source_path=video.source_path,
            status=video.status,
            error_message=video.error_message,
            duration_seconds=video.duration_seconds,
            export_dir=video.export_dir,
        )
        for video in videos
    ]


@router.post("/videos/process", response_model=ProcessVideoResponse)
def process_local_video(
    payload: ProcessVideoRequest,
    db: Session = Depends(get_db),
) -> ProcessVideoResponse:
    try:
        return process_video(db, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaProcessingError as exc:
        raise HTTPException(status_code=422, detail=f"FFmpeg failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
