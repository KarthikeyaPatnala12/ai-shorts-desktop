import unicodedata

from backend.app.schemas import LanguageProfile, TranscriptSegment


LANGUAGE_PROFILES = [
    LanguageProfile(code="auto", name="Auto detect", supports_romanization=False, profile_size_mb=0),
    LanguageProfile(code="en", name="English", supports_romanization=False, profile_size_mb=0),
    LanguageProfile(code="es", name="Spanish", supports_romanization=False, profile_size_mb=2),
    LanguageProfile(code="fr", name="French", supports_romanization=False, profile_size_mb=2),
    LanguageProfile(code="hi", name="Hindi", supports_romanization=True, profile_size_mb=3),
    LanguageProfile(code="ja", name="Japanese", supports_romanization=False, profile_size_mb=3),
    LanguageProfile(code="te", name="Telugu", supports_romanization=True, profile_size_mb=3),
]

def list_language_profiles() -> list[LanguageProfile]:
    return LANGUAGE_PROFILES


def prepare_caption_segments(
    segments: list[TranscriptSegment],
    caption_mode: str,
    source_language: str | None,
) -> list[TranscriptSegment]:
    if caption_mode != "romanized":
        return segments

    language = (source_language or "").lower()
    return [
        TranscriptSegment(
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=romanize_text(segment.text, language),
        )
        for segment in segments
    ]


def romanize_text(text: str, language: str) -> str:
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        return text

    source_scheme = None
    if language.startswith("hi"):
        source_scheme = sanscript.DEVANAGARI
    elif language.startswith("te"):
        source_scheme = sanscript.TELUGU

    if source_scheme is None:
        return text

    romanized = transliterate(text, source_scheme, sanscript.ITRANS)
    return _make_mobile_readable_romanization(romanized)


def _make_mobile_readable_romanization(text: str) -> str:
    replacements = {
        "A": "aa",
        "I": "ee",
        "U": "oo",
        "RRi": "ri",
        "M": "n",
        "~N": "n",
        "JN": "gy",
        "Sh": "sh",
        "T": "t",
        "D": "d",
        "N": "n",
        "L": "l",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())
