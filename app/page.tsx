"use client";

import { useEffect, useMemo, useState } from "react";

type ProcessedClip = {
  id: number;
  start_seconds: number;
  end_seconds: number;
  score: number;
  reason: string;
  subtitle_path: string;
  render_path: string;
};

type ProcessResponse = {
  video_id: number;
  status: string;
  source_path: string;
  duration_seconds: number | null;
  export_dir: string;
  clips: ProcessedClip[];
};

type DownloadResponse = {
  status: string;
  url: string;
  title: string | null;
  output_path: string;
  resolution: string;
};

type VideoSummary = {
  id: number;
  title: string | null;
  source_path: string;
  status: string;
  error_message: string | null;
  duration_seconds: number | null;
  export_dir: string | null;
};

type LanguageProfile = {
  code: string;
  name: string;
  supports_translation_to_english: boolean;
  supports_romanization: boolean;
  profile_size_mb: number;
};

type HardwareProfile = {
  accelerator: string;
  recommended_whisper_device: string;
  recommended_compute_type: string;
  recommended_model: string;
  notes: string[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [videoPath, setVideoPath] = useState("");
  const [downloadUrl, setDownloadUrl] = useState("");
  const [downloadResolution, setDownloadResolution] = useState<"best" | "2160" | "1440" | "1080" | "720" | "480">(
    "best"
  );
  const [clipCount, setClipCount] = useState(5);
  const [minClipSeconds, setMinClipSeconds] = useState(45);
  const [maxClipSeconds, setMaxClipSeconds] = useState(180);
  const [sourceLanguage, setSourceLanguage] = useState("auto");
  const [captionMode, setCaptionMode] = useState<"source" | "english" | "romanized">("source");
  const [status, setStatus] = useState("Idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [recentVideos, setRecentVideos] = useState<VideoSummary[]>([]);
  const [languages, setLanguages] = useState<LanguageProfile[]>([]);
  const [hardwareProfile, setHardwareProfile] = useState<HardwareProfile | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const canProcess = useMemo(
    () => videoPath.trim().length > 0 && !isProcessing,
    [videoPath, isProcessing]
  );

  useEffect(() => {
    void loadRecentVideos();
    void loadLanguages();
    void loadHardwareProfile();
  }, []);

  async function loadRecentVideos() {
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos`);
      if (!response.ok) {
        return;
      }
      setRecentVideos(await response.json());
    } catch {
      // Backend may not be running yet; the run action will show a concrete error.
    }
  }

  async function loadLanguages() {
    try {
      const response = await fetch(`${apiBaseUrl}/api/languages`);
      if (response.ok) {
        setLanguages(await response.json());
      }
    } catch {
      setLanguages([]);
    }
  }

  async function loadHardwareProfile() {
    try {
      const response = await fetch(`${apiBaseUrl}/api/system/profile`);
      if (response.ok) {
        setHardwareProfile(await response.json());
      }
    } catch {
      setHardwareProfile(null);
    }
  }

  async function pickVideo() {
    setError("");
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({
        multiple: false,
        filters: [
          {
            name: "Videos",
            extensions: ["mp4", "mov", "mkv", "webm", "avi", "m4v"]
          }
        ]
      });
      if (typeof selected === "string") {
        setVideoPath(selected);
      }
    } catch {
      setError("Tauri file picker is available in the desktop app. Paste a local video path for browser testing.");
    }
  }

  async function processVideo() {
    if (!canProcess) {
      return;
    }

    setIsProcessing(true);
    setError("");
    setResult(null);
    setStatus("Processing video locally. This can take several minutes for long files.");

    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/process`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          video_path: videoPath.trim(),
          clip_count: clipCount,
          min_clip_seconds: minClipSeconds,
          max_clip_seconds: maxClipSeconds,
          source_language: sourceLanguage,
          caption_mode: captionMode,
          target_language: "en"
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Processing failed.");
      }

      setResult(payload);
      setStatus(`Completed ${payload.clips.length} clips.`);
      await loadRecentVideos();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Processing failed.";
      setStatus("Failed");
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }

  async function downloadVideo() {
    if (!downloadUrl.trim() || isDownloading) {
      return;
    }

    setIsDownloading(true);
    setError("");
    setStatus("Downloading video locally with yt-dlp.");

    try {
      const response = await fetch(`${apiBaseUrl}/api/downloads/video`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          url: downloadUrl.trim(),
          resolution: downloadResolution
        })
      });
      const payload: DownloadResponse | { detail?: string } = await response.json();
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Download failed." : "Download failed.");
      }
      const downloaded = payload as DownloadResponse;
      setVideoPath(downloaded.output_path);
      setStatus(`Downloaded ${downloaded.title ?? "video"} at ${downloaded.resolution}.`);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Download failed.";
      setStatus("Failed");
      setError(message);
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <main className="min-h-screen bg-ink text-slate-100">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6">
        <header className="flex flex-col gap-4 border-b border-line pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="mb-2 text-xs font-bold uppercase text-mint">AI Shorts Repurposing</p>
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight text-white">
              Turn one local long-form video into captioned vertical clips.
            </h1>
          </div>
          <div className="rounded-md border border-line bg-panel px-4 py-3 text-sm text-slate-300">
            Backend: <span className="text-slate-100">{apiBaseUrl}</span>
          </div>
        </header>

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
          <div className="rounded-lg border border-line bg-panel p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-white">Source Video</h2>
                <p className="text-sm text-slate-400">Choose a local file in Tauri or paste an absolute path.</p>
              </div>
              <button
                type="button"
                onClick={pickVideo}
                className="h-10 rounded-md bg-mint px-4 text-sm font-bold text-ink"
              >
                Select File
              </button>
            </div>

            <label className="block text-sm font-medium text-slate-200" htmlFor="video-path">
              Local video path
            </label>
            <input
              id="video-path"
              value={videoPath}
              onChange={(event) => setVideoPath(event.target.value)}
              placeholder="C:\\Videos\\podcast-episode.mp4"
              className="mt-2 h-11 w-full rounded-md border border-line bg-ink px-3 text-sm text-white outline-none focus:border-mint"
            />

            <div className="mt-5 rounded-md border border-line bg-ink p-4">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px_120px]">
                <label className="block text-sm font-medium text-slate-200" htmlFor="download-url">
                  YouTube or video URL
                  <input
                    id="download-url"
                    value={downloadUrl}
                    onChange={(event) => setDownloadUrl(event.target.value)}
                    placeholder="https://www.youtube.com/watch?v=..."
                    className="mt-2 h-10 w-full rounded-md border border-line bg-panel px-3 text-sm text-white outline-none focus:border-mint"
                  />
                </label>
                <label className="block text-sm font-medium text-slate-200">
                  Quality
                  <select
                    value={downloadResolution}
                    onChange={(event) =>
                      setDownloadResolution(
                        event.target.value as "best" | "2160" | "1440" | "1080" | "720" | "480"
                      )
                    }
                    className="mt-2 h-10 w-full rounded-md border border-line bg-panel px-3 text-sm text-white outline-none focus:border-mint"
                  >
                    <option value="best">Best</option>
                    <option value="2160">4K</option>
                    <option value="1440">1440p</option>
                    <option value="1080">1080p</option>
                    <option value="720">720p</option>
                    <option value="480">480p</option>
                  </select>
                </label>
                <button
                  type="button"
                  disabled={!downloadUrl.trim() || isDownloading || isProcessing}
                  onClick={downloadVideo}
                  className="mt-7 h-10 rounded-md bg-slate-100 px-3 text-sm font-bold text-ink disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDownloading ? "Saving..." : "Download"}
                </button>
              </div>
              <p className="mt-3 text-xs text-slate-400">
                Downloads are saved locally and should only be used for videos you own or have permission to process.
              </p>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <NumberField label="Clips" min={1} max={5} value={clipCount} onChange={setClipCount} />
              <NumberField
                label="Min seconds"
                min={5}
                max={180}
                value={minClipSeconds}
                onChange={setMinClipSeconds}
              />
              <NumberField
                label="Max seconds"
                min={10}
                max={180}
                value={maxClipSeconds}
                onChange={setMaxClipSeconds}
              />
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-slate-200">
                Source language
                <select
                  value={sourceLanguage}
                  onChange={(event) => setSourceLanguage(event.target.value)}
                  className="mt-2 h-10 w-full rounded-md border border-line bg-ink px-3 text-sm text-white outline-none focus:border-mint"
                >
                  {(languages.length ? languages : [{ code: "auto", name: "Auto detect" } as LanguageProfile]).map(
                    (language) => (
                      <option key={language.code} value={language.code}>
                        {language.name}
                      </option>
                    )
                  )}
                </select>
              </label>

              <label className="block text-sm font-medium text-slate-200">
                Caption output
                <select
                  value={captionMode}
                  onChange={(event) => setCaptionMode(event.target.value as "source" | "english" | "romanized")}
                  className="mt-2 h-10 w-full rounded-md border border-line bg-ink px-3 text-sm text-white outline-none focus:border-mint"
                >
                  <option value="source">Original language</option>
                  <option value="english">Translate to English</option>
                  <option value="romanized">Romanized captions</option>
                </select>
              </label>
            </div>

            {hardwareProfile ? (
              <div className="mt-5 rounded-md border border-line bg-ink p-3 text-sm text-slate-300">
                Hardware: <span className="text-slate-100">{hardwareProfile.accelerator}</span> · Whisper{" "}
                <span className="text-slate-100">
                  {hardwareProfile.recommended_model}/{hardwareProfile.recommended_whisper_device}/
                  {hardwareProfile.recommended_compute_type}
                </span>
              </div>
            ) : null}

            <button
              type="button"
              disabled={!canProcess}
              onClick={processVideo}
              className="mt-6 h-11 w-full rounded-md bg-mint text-sm font-bold text-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isProcessing ? "Processing..." : "Generate Shorts"}
            </button>

            <div className="mt-5 rounded-md border border-line bg-ink p-4">
              <div className="text-sm font-semibold text-white">{status}</div>
              {error ? <p className="mt-2 text-sm text-red-300">{error}</p> : null}
              {isProcessing ? (
                <p className="mt-2 text-sm text-slate-400">
                  Pipeline: FFmpeg audio extraction, faster-whisper transcription, heuristic clip scoring,
                  translation/romanized ASS captions, vertical FFmpeg render, caption burn-in.
                </p>
              ) : null}
            </div>
          </div>

          <div className="rounded-lg border border-line bg-panel p-5">
            <h2 className="text-lg font-semibold text-white">Exports</h2>
            {!result ? (
              <p className="mt-2 text-sm text-slate-400">
                Generated MP4 clips and styled ASS caption files will appear here after processing.
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                <div className="rounded-md border border-line bg-ink p-3 text-sm text-slate-300">
                  Export folder: <span className="text-slate-100">{result.export_dir}</span>
                </div>
                {result.clips.map((clip, index) => (
                  <article key={clip.id} className="rounded-md border border-line bg-ink p-4">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="font-semibold text-white">Clip {index + 1}</h3>
                      <span className="text-sm text-mint">{Math.round(clip.score * 100)}%</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">
                      {formatTime(clip.start_seconds)} to {formatTime(clip.end_seconds)} · {clip.reason}
                    </p>
                    <p className="mt-3 break-all text-sm text-slate-200">{clip.render_path}</p>
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-lg border border-line bg-panel p-5">
          <h2 className="text-lg font-semibold text-white">Recent Local Runs</h2>
          <div className="mt-4 overflow-hidden rounded-md border border-line">
            {recentVideos.length === 0 ? (
              <div className="bg-ink p-4 text-sm text-slate-400">No processed videos yet.</div>
            ) : (
              recentVideos.map((video) => (
                <div
                  key={video.id}
                  className="grid gap-2 border-b border-line bg-ink p-4 text-sm last:border-b-0 md:grid-cols-[1fr_130px_1fr]"
                >
                  <span className="break-all text-slate-100">{video.title ?? video.source_path}</span>
                  <span className="text-slate-300">{video.status}</span>
                  <span className="break-all text-slate-400">{video.export_dir ?? video.error_message ?? ""}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function NumberField({
  label,
  min,
  max,
  value,
  onChange
}: {
  label: string;
  min: number;
  max: number;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-sm font-medium text-slate-200">
      {label}
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 h-10 w-full rounded-md border border-line bg-ink px-3 text-sm text-white outline-none focus:border-mint"
      />
    </label>
  );
}

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}
