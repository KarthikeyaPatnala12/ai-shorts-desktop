from fastapi import APIRouter, HTTPException

from backend.app.schemas import VideoDownloadRequest, VideoDownloadResponse
from backend.app.services.downloader import DownloadError, download_video

router = APIRouter()


@router.post("/downloads/video", response_model=VideoDownloadResponse)
def download_remote_video(payload: VideoDownloadRequest) -> VideoDownloadResponse:
    try:
        output_path, title = download_video(
            url=str(payload.url),
            resolution=payload.resolution,
            audio_only=payload.audio_only,
        )
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VideoDownloadResponse(
        status="completed",
        url=str(payload.url),
        title=title,
        output_path=str(output_path),
        resolution=payload.resolution,
    )
