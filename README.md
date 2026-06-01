# AI Shorts Repurposing Desktop MVP

Local-first desktop app for turning a long video into 3-5 vertical short clips with burned-in captions. The MVP keeps all media, transcripts, project data, and exports on the user's machine.

## Stack

- Tauri desktop shell
- Next.js + Tailwind frontend
- Python FastAPI local backend
- SQLite project database
- FFmpeg and FFprobe for media processing
- faster-whisper for local transcription
- yt-dlp for optional local video URL downloads
- Optional English translation and romanized captions for selected languages

No cloud upload, authentication, payments, collaboration, social scheduling, or timeline editor are included.

## Project Structure

```text
.
├── app/                         # Next.js frontend screens
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI app
│       ├── models.py            # SQLite models
│       ├── routers/             # API endpoints
│       └── services/            # Processing pipeline modules
│           ├── transcription.py
│           ├── clip_detection.py
│           ├── rendering.py
│           ├── subtitles.py
│           ├── media.py
│           └── pipeline.py
├── src-tauri/                   # Tauri desktop wrapper
├── models/                      # Reserved for local model files
├── exports/                     # Generated MP4/ASS output folders
├── downloads/                   # Optional URL downloads saved locally
├── temp/                        # Per-run audio/temp files
├── config.example.json
├── .env.example
└── README.md
```

## Prerequisites

- Node.js 20+
- Rust stable and Tauri OS prerequisites
- Python 3.11+
- FFmpeg and FFprobe available on `PATH`

Check FFmpeg:

```powershell
ffmpeg -version
ffprobe -version
```

## Setup

```powershell
Copy-Item .env.example .env
npm install
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r backend\\requirements.txt
```

For lower-memory machines, keep `AI_SHORTS_WHISPER_MODEL=base` or use `tiny`. CPU transcription is the default because it works without CUDA. For better transcripts, use `small` or `medium` if your machine can handle it. To use an NVIDIA GPU later, set `AI_SHORTS_WHISPER_DEVICE=cuda` after installing the CUDA/cuDNN libraries required by CTranslate2.

## Run Backend

```powershell
.\\.venv\\Scripts\\Activate.ps1
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Run Frontend

```powershell
npm run dev
```

Open `http://localhost:3000`.

## Run Desktop App

Start the backend first, then run:

```powershell
npm run tauri:dev
```

The desktop UI can open the native file picker. Browser-only development can still paste an absolute local video path.

## Main Pipeline

`POST /api/videos/process`

Request:

```json
{
  "video_path": "C:\\Videos\\long-video.mp4",
  "clip_count": 5,
  "min_clip_seconds": 45,
  "max_clip_seconds": 180
}
```

Processing steps:

1. Validate the local source video path.
2. Create a SQLite video record.
3. Probe duration with FFprobe.
4. Extract mono 16 kHz WAV audio with FFmpeg.
5. Transcribe audio with faster-whisper.
6. Build a full-video context summary from transcript keywords, topic blocks, and viral pattern signals.
7. Segment the transcript into complete topic/conversation windows.
8. Score candidate clips with hook, duration, density, full-video topic relevance, viral pattern, and standalone-idea signals.
9. Refine start/end boundaries to reduce weak openings and preserve setup/payoff.
10. Generate styled ASS captions per selected clip in source language, English translation, or romanized text.
11. Sample frames for face detection, cut each clip, crop around the likely speaker, convert to 1080x1920 vertical video, clean the old subtitle band, and burn captions with FFmpeg.
12. Save MP4 and ASS files under `exports/<video-name>-<run-id>/`.

Each run also writes `context-summary.txt` in the export folder so the detected full-video context can be inspected.

Response:

```json
{
  "video_id": 1,
  "status": "completed",
  "source_path": "C:\\Videos\\long-video.mp4",
  "duration_seconds": 3600.0,
  "export_dir": "C:\\path\\to\\exports\\long-video-a1b2c3d4e5",
  "clips": [
    {
      "id": 1,
      "start_seconds": 42.0,
      "end_seconds": 88.0,
      "score": 0.74,
      "reason": "2 hook terms, 46s duration, dense transcript window",
      "subtitle_path": "C:\\path\\to\\clip-01.ass",
      "render_path": "C:\\path\\to\\clip-01.mp4"
    }
  ]
}
```

## Other API Endpoints

- `GET /health`
- `GET /api/videos`
- `POST /api/downloads/video`
- `POST /transcription`
- `POST /clips/detect`
- `POST /subtitles`
- `POST /render`
- `GET /api/languages`
- `GET /api/system/profile`

The older module endpoints are kept for isolated testing. The desktop UI uses `/api/videos/process`.

## Optional URL Downloading

The desktop UI can paste a YouTube/video URL and download it locally before processing. The backend uses `yt-dlp` through Python:

```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "resolution": "1080"
}
```

Supported `resolution` values are `best`, `2160`, `1440`, `1080`, `720`, and `480`. Downloads are saved under `downloads/`, then the returned `output_path` is used as the source video path. Use this only for videos you own or have permission to process, and for sites whose terms allow downloading.

## Configuration

Environment variables are read from `.env`:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
AI_SHORTS_DATABASE_URL=sqlite:///./data/ai_shorts.sqlite3
AI_SHORTS_WORKSPACE_DIR=./workspace
AI_SHORTS_EXPORTS_DIR=./exports
AI_SHORTS_TEMP_DIR=./temp
AI_SHORTS_DOWNLOADS_DIR=./downloads
AI_SHORTS_WHISPER_MODEL=base
AI_SHORTS_WHISPER_DEVICE=cpu
AI_SHORTS_WHISPER_COMPUTE_TYPE=int8
AI_SHORTS_CLIP_COUNT=5
AI_SHORTS_MIN_CLIP_SECONDS=45
AI_SHORTS_MAX_CLIP_SECONDS=180
```

`config.example.json` mirrors these settings for future app-level config loading.

## Language and Hardware Modes

The UI can now request three caption modes:

- `source`: transcribe and caption in the detected/source language.
- `english`: use faster-whisper translation mode and caption the clip in English.
- `romanized`: transcribe in the source language and convert supported scripts, currently Hindi/Devanagari and Telugu, into a rough Roman alphabet caption style.

The language profile endpoint is lightweight metadata for now. It models the future small-installer behavior where language resources can be downloaded on demand rather than bundled.

The hardware profile endpoint detects CPU, NVIDIA CUDA availability, or Apple Silicon and returns conservative recommended Whisper settings. The current backend still reads actual runtime settings from `.env`.

## Current Limitations

- Processing is synchronous, so the first MVP request blocks until all clips are rendered.
- The heuristic scorer is intentionally simple and does not call an LLM.
- Captions are generated as ASS with karaoke-style active text highlighting, pop/fade motion, SF Pro Display from `sf-pro-display/` when present, and bundled Montserrat Bold fallback from `assets/fonts/`.
- Existing SQLite schemas are not migrated; delete `data/ai_shorts.sqlite3` during early MVP iteration if models change.

## Next Steps

1. Move processing into a background job queue with progress updates.
2. Add preview playback for exported clips.
3. Add editable subtitle style presets.
4. Add optional Ollama/Qwen scoring behind a local-only setting.
5. Add lightweight migration handling before real user data matters.
