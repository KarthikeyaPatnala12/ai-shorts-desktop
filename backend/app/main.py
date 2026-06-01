from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import init_db
from backend.app.routers import clips, downloads, pipeline, render, subtitles, system, transcription
from backend.app.schemas import HealthResponse

app = FastAPI(title="AI Shorts Desktop API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


app.include_router(transcription.router, prefix="/transcription", tags=["transcription"])
app.include_router(clips.router, prefix="/clips", tags=["clips"])
app.include_router(subtitles.router, prefix="/subtitles", tags=["subtitles"])
app.include_router(render.router, prefix="/render", tags=["render"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])
app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
