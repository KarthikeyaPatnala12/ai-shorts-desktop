from pathlib import Path

from backend.app.config import get_settings
from backend.app.schemas import TranscriptSegment, TranscriptionResponse

_MODEL = None
_MODEL_NAME = None
_MODEL_DEVICE = None


def transcribe_video(
    video_path: str,
    language: str | None = None,
    task: str = "transcribe",
) -> TranscriptionResponse:
    return transcribe_audio(video_path, language=language, task=task)


def transcribe_audio(
    audio_path: str | Path,
    language: str | None = None,
    task: str = "transcribe",
) -> TranscriptionResponse:
    source = Path(audio_path)
    if not source.exists():
        raise FileNotFoundError(f"Audio file not found: {source}")

    try:
        segments_iter, info = _transcribe_with_model(source, language=language, task=task)
    except RuntimeError as exc:
        if not _is_cuda_runtime_error(exc):
            raise
        segments_iter, info = _transcribe_with_cpu_fallback(source, language=language, task=task)

    segments = [
        TranscriptSegment(
            start_seconds=float(segment.start),
            end_seconds=float(segment.end),
            text=segment.text.strip(),
        )
        for segment in segments_iter
        if segment.text.strip()
    ]
    return TranscriptionResponse(language=getattr(info, "language", None), task=task, segments=segments)


def _transcribe_with_model(source: Path, language: str | None, task: str):
    model = _get_model()
    return model.transcribe(
        str(source),
        language=None if language in {None, "auto"} else language,
        task=task,
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
    )


def _transcribe_with_cpu_fallback(source: Path, language: str | None, task: str):
    global _MODEL, _MODEL_DEVICE
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    settings = get_settings()
    _MODEL = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    _MODEL_DEVICE = "cpu"
    return _MODEL.transcribe(
        str(source),
        language=None if language in {None, "auto"} else language,
        task=task,
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
    )


def _get_model():
    global _MODEL, _MODEL_NAME, _MODEL_DEVICE
    settings = get_settings()
    if (
        _MODEL is not None
        and _MODEL_NAME == settings.whisper_model
        and _MODEL_DEVICE == settings.whisper_device
    ):
        return _MODEL

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    _MODEL = _load_model(
        WhisperModel,
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    _MODEL_NAME = settings.whisper_model
    _MODEL_DEVICE = settings.whisper_device
    return _MODEL


def _load_model(whisper_model_cls, model_name: str, device: str, compute_type: str):
    try:
        return whisper_model_cls(model_name, device=device, compute_type=compute_type)
    except RuntimeError as exc:
        if device == "cpu" or not _is_cuda_runtime_error(exc):
            raise
        return whisper_model_cls(model_name, device="cpu", compute_type="int8")


def _is_cuda_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc).lower()
    return "cublas" in message or "cudnn" in message or "cuda" in message
