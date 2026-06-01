import subprocess
from pathlib import Path

from backend.app.services.media import run_command
from backend.app.services.speaker_framing import CropWindow, RenderLayout, detect_render_layout

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
SF_PRO_FONTS_DIR = PROJECT_ROOT / "sf-pro-display"


def build_render_command(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    subtitle_path: str | None,
    output_path: str,
) -> list[str]:
    duration = max(0.0, end_seconds - start_seconds)
    layout = detect_render_layout(video_path, start_seconds, end_seconds)
    if layout.mode == "two_person_split" and layout.primary_crop and layout.secondary_crop:
        return _build_split_screen_command(
            video_path=video_path,
            start_seconds=start_seconds,
            duration=duration,
            subtitle_path=subtitle_path,
            output_path=output_path,
            layout=layout,
        )

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-i",
        video_path,
        "-t",
        str(duration),
        "-vf",
        _video_filter(subtitle_path, layout.primary_crop),
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        output_path,
    ]
    return command


def _build_split_screen_command(
    video_path: str,
    start_seconds: float,
    duration: float,
    subtitle_path: str | None,
    output_path: str,
    layout: RenderLayout,
) -> list[str]:
    assert layout.primary_crop is not None
    assert layout.secondary_crop is not None
    return [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-i",
        video_path,
        "-t",
        str(duration),
        "-filter_complex",
        _split_screen_filter(subtitle_path, layout.primary_crop, layout.secondary_crop),
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]


def render_clip(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg for a clip render after command preview is approved by the caller."""
    return subprocess.run(command, check=True, capture_output=True, text=True)


def render_vertical_clip(
    video_path: str | Path,
    start_seconds: float,
    end_seconds: float,
    subtitle_path: str | Path | None,
    output_path: str | Path,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = build_render_command(
        video_path=str(video_path),
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        subtitle_path=str(subtitle_path) if subtitle_path else None,
        output_path=str(output),
    )
    run_command(command)
    return output


def _video_filter(subtitle_path: str | None, crop_window: CropWindow | None = None) -> str:
    base_filter = _base_video_filter(crop_window)
    caption_filter = _caption_filter(subtitle_path)
    return f"{base_filter},{caption_filter}" if caption_filter else base_filter


def _split_screen_filter(
    subtitle_path: str | None,
    top_crop: CropWindow,
    bottom_crop: CropWindow,
) -> str:
    stacked_filter = (
        f"[0:v]{_crop_filter(top_crop)},scale=1080:960[top];"
        f"[0:v]{_crop_filter(bottom_crop)},scale=1080:960[bottom];"
        "[top][bottom]vstack=inputs=2[stacked]"
    )
    caption_filter = _caption_filter(subtitle_path)
    if caption_filter:
        return f"{stacked_filter};[stacked]{caption_filter}[v]"
    return f"{stacked_filter};[stacked]null[v]"


def _caption_filter(subtitle_path: str | None) -> str | None:
    if not subtitle_path:
        return None
    escaped_path = _escape_subtitle_path(subtitle_path)
    if subtitle_path.lower().endswith(".ass"):
        fonts_dir = _escape_subtitle_path(str(_subtitle_fonts_dir()))
        return (
            "drawbox=x=0:y=1535:w=1080:h=255:color=black@0.24:t=fill,"
            f"subtitles='{escaped_path}':fontsdir='{fonts_dir}'"
        )
    return f"subtitles='{escaped_path}':force_style='Fontsize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=140'"


def _escape_subtitle_path(subtitle_path: str) -> str:
    return subtitle_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _subtitle_fonts_dir() -> Path:
    if SF_PRO_FONTS_DIR.exists():
        return SF_PRO_FONTS_DIR
    return FONTS_DIR


def _base_video_filter(crop_window: CropWindow | None) -> str:
    if crop_window is None:
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    return (
        f"{_crop_filter(crop_window)},"
        "scale=1080:1920"
    )


def _crop_filter(crop_window: CropWindow) -> str:
    return f"crop={crop_window.width}:{crop_window.height}:{crop_window.x}:{crop_window.y}"
