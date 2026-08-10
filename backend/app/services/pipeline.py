from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.config import get_settings
from backend.app.schemas import ProcessVideoRequest, ProcessVideoResponse, ProcessedClip, TranscriptSegment, ClipCandidate
from backend.app.services.clip_detection import detect_clips
from backend.app.services.context_analysis import build_video_context, describe_context
from backend.app.services.language_profiles import prepare_caption_segments
from backend.app.services.media import extract_audio, probe_duration
from backend.app.services.rendering import render_vertical_clip
from backend.app.services.subtitles import generate_subtitles
from backend.app.services.transcription import transcribe_audio


def process_video(db: Session, payload: ProcessVideoRequest) -> ProcessVideoResponse:
    settings = get_settings()
    source = Path(payload.video_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Video file not found: {source}")

    run_id = uuid4().hex[:10]
    export_dir = (settings.exports_dir / f"{source.stem}-{run_id}").resolve()
    temp_dir = (settings.temp_dir / run_id).resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    video = models.Video(
        source_path=str(source),
        title=source.stem,
        status="processing",
        duration_seconds=probe_duration(source),
        export_dir=str(export_dir),
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    try:
        audio_path = extract_audio(source, temp_dir / "audio.wav")
        transcription_task = "translate" if payload.caption_mode == "english" else "transcribe"
        transcript = transcribe_audio(
            audio_path,
            language=payload.source_language,
            task=transcription_task,
        )
        _persist_segments(db, video.id, transcript.segments)
        video_context = build_video_context(transcript.segments)
        (export_dir / "context-summary.txt").write_text(describe_context(video_context), encoding="utf-8")

        candidates = detect_clips(
            transcript.segments,
            target_duration_seconds=min(120, payload.max_clip_seconds),
            clip_count=payload.clip_count,
            min_clip_seconds=payload.min_clip_seconds,
            max_clip_seconds=min(180, payload.max_clip_seconds),
            context=video_context,
        )

        def process_candidate(index: int, candidate: ClipCandidate) -> tuple[int, ClipCandidate, Path, Path]:
            clip_segments = _segments_for_clip(
                transcript.segments,
                candidate.start_seconds,
                candidate.end_seconds,
            )
            local_segments = [
                TranscriptSegment(
                    start_seconds=max(0.0, segment.start_seconds - candidate.start_seconds),
                    end_seconds=max(0.0, segment.end_seconds - candidate.start_seconds),
                    text=segment.text,
                )
                for segment in clip_segments
            ]
            caption_segments = prepare_caption_segments(
                local_segments,
                caption_mode=payload.caption_mode,
                source_language=transcript.language or payload.source_language,
            )
            subtitle_path = export_dir / f"clip-{index:02}.ass"
            subtitle_path.write_text(generate_subtitles(caption_segments, "ass"), encoding="utf-8")

            render_path = export_dir / f"clip-{index:02}.mp4"
            render_vertical_clip(
                video_path=source,
                start_seconds=candidate.start_seconds,
                end_seconds=candidate.end_seconds,
                subtitle_path=subtitle_path,
                output_path=render_path,
            )
            return index, candidate, subtitle_path, render_path

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for index, candidate in enumerate(candidates, start=1):
                futures.append(executor.submit(process_candidate, index, candidate))

            results = [future.result() for future in futures]

        processed_clips: list[ProcessedClip] = []
        for index, candidate, subtitle_path, render_path in results:
            clip = models.Clip(
                video_id=video.id,
                start_seconds=candidate.start_seconds,
                end_seconds=candidate.end_seconds,
                score=candidate.score,
                reason=candidate.reason,
                subtitle_path=str(subtitle_path),
                render_path=str(render_path),
                status="exported",
            )
            db.add(clip)
            db.commit()
            db.refresh(clip)
            processed_clips.append(
                ProcessedClip(
                    id=clip.id,
                    start_seconds=clip.start_seconds,
                    end_seconds=clip.end_seconds,
                    score=clip.score,
                    reason=clip.reason or "",
                    subtitle_path=clip.subtitle_path or "",
                    render_path=clip.render_path or "",
                )
            )

        video.status = "completed"
        db.add(video)
        db.commit()

        return ProcessVideoResponse(
            video_id=video.id,
            status=video.status,
            source_path=video.source_path,
            duration_seconds=video.duration_seconds,
            export_dir=str(export_dir),
            clips=processed_clips,
        )
    except Exception as exc:
        video.status = "failed"
        video.error_message = str(exc)
        db.add(video)
        db.commit()
        raise


def _persist_segments(db: Session, video_id: int, segments: list[TranscriptSegment]) -> None:
    for segment in segments:
        db.add(
            models.TranscriptSegment(
                video_id=video_id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
            )
        )
    db.commit()


def _segments_for_clip(
    segments: list[TranscriptSegment],
    start_seconds: float,
    end_seconds: float,
) -> list[TranscriptSegment]:
    return [
        segment
        for segment in segments
        if segment.end_seconds >= start_seconds and segment.start_seconds <= end_seconds
    ]
