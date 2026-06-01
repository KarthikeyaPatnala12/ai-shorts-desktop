from pathlib import Path

from backend.app.schemas import TranscriptSegment

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSETS_FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
SF_PRO_FONTS_DIR = PROJECT_ROOT / "sf-pro-display"


def generate_subtitles(segments: list[TranscriptSegment], subtitle_format: str = "srt") -> str:
    """Generate subtitle text from transcript segments."""
    normalized_format = subtitle_format.lower()
    if normalized_format == "ass":
        return generate_ass_subtitles(segments)
    if normalized_format != "srt":
        raise ValueError("Only SRT and ASS subtitle generation are implemented.")

    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_format_srt_time(segment.start_seconds)} --> {_format_srt_time(segment.end_seconds)}",
                    segment.text.strip(),
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def generate_ass_subtitles(segments: list[TranscriptSegment]) -> str:
    """Generate punchy vertical-video captions with approximate karaoke timing."""
    events = []
    for segment in _caption_chunks(segments):
        text = _karaoke_text(segment.text, segment.end_seconds - segment.start_seconds)
        events.append(
            ",".join(
                [
                    "Dialogue: 0",
                    _format_ass_time(segment.start_seconds),
                    _format_ass_time(segment.end_seconds),
                    "ViralCaption",
                    "",
                    "0",
                    "0",
                    "0",
                    "",
                    (
                        "{\\an2\\pos(540,1405)\\fad(80,80)"
                        "\\fscx94\\fscy94\\t(0,120,\\fscx104\\fscy104)}"
                        f"{text}"
                    ),
                ]
            )
        )

    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 0",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                f"Style: ViralCaption,{_caption_font_name()},78,&H0000E7FF,&H00FFFFFF,"
                "&H00111111,&H00111111,-1,0,0,0,100,100,0,0,1,5,3,"
                "2,90,90,260,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )


def _format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _format_ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours:d}:{minutes:02}:{secs:02}.{centis:02}"


def _caption_chunks(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    chunks: list[TranscriptSegment] = []
    for segment in segments:
        words = segment.text.strip().split()
        if not words:
            continue
        if len(words) <= 8:
            chunks.append(segment)
            continue

        duration = max(0.1, segment.end_seconds - segment.start_seconds)
        word_seconds = duration / len(words)
        for start_index in range(0, len(words), 7):
            chunk_words = words[start_index : start_index + 7]
            chunk_start = segment.start_seconds + start_index * word_seconds
            chunk_end = min(segment.end_seconds, chunk_start + len(chunk_words) * word_seconds)
            chunks.append(
                TranscriptSegment(
                    start_seconds=chunk_start,
                    end_seconds=chunk_end,
                    text=" ".join(chunk_words),
                )
            )
    return chunks


def _karaoke_text(text: str, duration_seconds: float) -> str:
    words = [_escape_ass_text(word) for word in text.strip().split()]
    if not words:
        return ""

    centiseconds = max(4, int(round(duration_seconds * 100 / len(words))))
    return " ".join(f"{{\\kf{centiseconds}}}{word.upper()}" for word in words)


def _escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
    )


def _caption_font_name() -> str:
    if _font_exists("SF Pro") or _font_exists("SFPRODISPLAY"):
        return "SF Pro Display"
    return "Montserrat"


def _font_exists(name: str) -> bool:
    windows_fonts = Path("C:/Windows/Fonts")
    candidates = []
    if windows_fonts.exists():
        candidates.extend(windows_fonts.glob("*.ttf"))
        candidates.extend(windows_fonts.glob("*.otf"))
    if ASSETS_FONTS_DIR.exists():
        candidates.extend(ASSETS_FONTS_DIR.glob("*.ttf"))
        candidates.extend(ASSETS_FONTS_DIR.glob("*.otf"))
    if SF_PRO_FONTS_DIR.exists():
        candidates.extend(SF_PRO_FONTS_DIR.glob("*.ttf"))
        candidates.extend(SF_PRO_FONTS_DIR.glob("*.otf"))
    normalized = name.lower().replace(" ", "")
    return any(normalized in font.stem.lower().replace(" ", "") for font in candidates)
