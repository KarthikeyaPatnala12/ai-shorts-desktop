import json
import re
import subprocess
import sys
from pathlib import Path

from backend.app.config import get_settings


class DownloadError(RuntimeError):
    pass


def download_video(url: str, resolution: str = "best", audio_only: bool = False) -> tuple[Path, str | None]:
    settings = get_settings()
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)

    info = _probe_video_info(url)
    title = _safe_title(info.get("title") or "downloaded-video")
    video_id = _safe_title(info.get("id") or "video")
    output_template = str(settings.downloads_dir / f"{title}-{video_id}.%(ext)s")

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--restrict-filenames",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
    ]
    if audio_only:
        command.extend(["-f", "bestaudio/best", "--extract-audio", "--audio-format", "m4a"])
    else:
        command.extend(["-f", _format_selector(resolution)])
    command.append(url)

    _run_ytdlp(command)
    downloaded_path = _find_downloaded_file(settings.downloads_dir, title, video_id)
    if downloaded_path is None:
        raise DownloadError("Download completed but the output file could not be located.")
    return downloaded_path, info.get("title")


def _probe_video_info(url: str) -> dict:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        url,
    ]
    result = _run_ytdlp(command)
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise DownloadError("yt-dlp returned invalid metadata.") from exc
    return payload if isinstance(payload, dict) else {}


def _format_selector(resolution: str) -> str:
    if resolution == "best":
        return "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
    max_height = int(resolution)
    return f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/b[height<={max_height}][ext=mp4]/bv*[height<={max_height}]+ba/b[height<={max_height}]"


def _run_ytdlp(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise DownloadError("Python executable was not found for yt-dlp.") from exc
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("Download timed out.") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "yt-dlp failed.").strip()
        raise DownloadError(message[-1200:])
    return result


def _find_downloaded_file(downloads_dir: Path, title: str, video_id: str) -> Path | None:
    candidates = sorted(
        downloads_dir.glob(f"{title}-{video_id}.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a"}:
            return candidate.resolve()
    return None


def _safe_title(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe[:120] or "video"
