from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str = "ok"


class TranscriptionRequest(BaseModel):
    video_path: str
    language: str | None = None
    task: Literal["transcribe", "translate"] = "transcribe"


class TranscriptSegment(BaseModel):
    start_seconds: float
    end_seconds: float
    text: str


class TranscriptionResponse(BaseModel):
    language: str | None = None
    task: str = "transcribe"
    segments: list[TranscriptSegment]


class ClipCandidate(BaseModel):
    start_seconds: float
    end_seconds: float
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class ClipDetectionRequest(BaseModel):
    segments: list[TranscriptSegment]
    target_duration_seconds: int = 120


class ClipDetectionResponse(BaseModel):
    clips: list[ClipCandidate]


class SubtitleRequest(BaseModel):
    segments: list[TranscriptSegment]
    format: str = "ass"


class SubtitleResponse(BaseModel):
    content: str


class RenderRequest(BaseModel):
    video_path: str
    start_seconds: float
    end_seconds: float
    subtitle_path: str | None = None
    output_path: str


class RenderResponse(BaseModel):
    output_path: str
    command: list[str]


class ProcessVideoRequest(BaseModel):
    video_path: str
    clip_count: int = Field(default=5, ge=1, le=5)
    min_clip_seconds: int = Field(default=45, ge=10, le=180)
    max_clip_seconds: int = Field(default=180, ge=30, le=180)
    source_language: str | None = None
    caption_mode: Literal["source", "english", "romanized"] = "source"
    target_language: str = "en"

    @model_validator(mode="after")
    def validate_duration_window(self) -> "ProcessVideoRequest":
        if self.min_clip_seconds > self.max_clip_seconds:
            raise ValueError("min_clip_seconds must be less than or equal to max_clip_seconds")
        return self


class VideoDownloadRequest(BaseModel):
    url: str = Field(min_length=8)
    resolution: Literal["best", "2160", "1440", "1080", "720", "480"] = "best"
    audio_only: bool = False


class VideoDownloadResponse(BaseModel):
    status: str
    url: str
    title: str | None = None
    output_path: str
    resolution: str


class ProcessedClip(BaseModel):
    id: int
    start_seconds: float
    end_seconds: float
    score: float
    reason: str
    subtitle_path: str
    render_path: str


class ProcessVideoResponse(BaseModel):
    video_id: int
    status: str
    source_path: str
    duration_seconds: float | None = None
    export_dir: str
    clips: list[ProcessedClip]


class VideoSummary(BaseModel):
    id: int
    title: str | None = None
    source_path: str
    status: str
    error_message: str | None = None
    duration_seconds: float | None = None
    export_dir: str | None = None


class LanguageProfile(BaseModel):
    code: str
    name: str
    supports_translation_to_english: bool = True
    supports_romanization: bool = False
    profile_size_mb: int = 0


class HardwareProfile(BaseModel):
    platform: str
    architecture: str
    accelerator: str
    recommended_whisper_device: str
    recommended_compute_type: str
    recommended_model: str
    notes: list[str]
