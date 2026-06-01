from collections import Counter
from dataclasses import dataclass

from backend.app.schemas import TranscriptSegment


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
    "about",
    "actually",
    "also",
    "can",
    "don't",
    "going",
    "got",
    "guess",
    "it's",
    "just",
    "kind",
    "know",
    "like",
    "maybe",
    "mean",
    "really",
    "right",
    "say",
    "something",
    "thing",
    "things",
    "think",
    "was",
    "yeah",
}

VIRAL_PATTERN_TERMS = {
    "contrarian claim": {
        "actually",
        "wrong",
        "truth",
        "myth",
        "believe",
        "rather",
        "instead",
        "but",
    },
    "big consequence": {
        "future",
        "change",
        "jobs",
        "money",
        "economy",
        "world",
        "humanity",
        "risk",
    },
    "simple mental model": {
        "simple",
        "basically",
        "means",
        "system",
        "information",
        "because",
        "example",
    },
    "conflict or tension": {
        "difficult",
        "problem",
        "argument",
        "disagree",
        "won't",
        "can't",
        "challenge",
    },
    "practical advice": {
        "should",
        "need",
        "must",
        "important",
        "advice",
        "learn",
        "focus",
    },
}


@dataclass(frozen=True)
class TopicBlock:
    start_seconds: float
    end_seconds: float
    keywords: list[str]
    summary: str

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class VideoContext:
    keywords: list[str]
    topic_blocks: list[TopicBlock]
    pattern_counts: dict[str, int]


def build_video_context(segments: list[TranscriptSegment]) -> VideoContext:
    if not segments:
        return VideoContext(keywords=[], topic_blocks=[], pattern_counts={})

    full_text = " ".join(segment.text for segment in segments)
    keywords = _top_keywords(full_text, limit=24)
    topic_blocks = _build_topic_blocks(segments)
    pattern_counts = {
        pattern: sum(1 for word in _words(full_text) if word in terms)
        for pattern, terms in VIRAL_PATTERN_TERMS.items()
    }
    return VideoContext(keywords=keywords, topic_blocks=topic_blocks, pattern_counts=pattern_counts)


def describe_context(context: VideoContext) -> str:
    top_topics = "; ".join(
        f"{_format_time(block.start_seconds)}-{_format_time(block.end_seconds)}: {', '.join(block.keywords[:4])}"
        for block in context.topic_blocks[:8]
    )
    top_patterns = sorted(context.pattern_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    patterns = ", ".join(pattern for pattern, count in top_patterns if count > 0) or "none detected"
    return f"keywords: {', '.join(context.keywords[:10])}; patterns: {patterns}; topics: {top_topics}"


def clip_context_features(text: str, context: VideoContext) -> tuple[float, list[str]]:
    words = _words(text)
    word_set = set(words)
    if not words:
        return 0.0, ["empty transcript window"]

    global_keyword_hits = [keyword for keyword in context.keywords[:16] if keyword in word_set]
    global_relevance = min(len(global_keyword_hits) / 5.0, 1.0)

    pattern_hits = []
    for pattern, terms in VIRAL_PATTERN_TERMS.items():
        hits = len(word_set & terms)
        if hits:
            pattern_hits.append((pattern, hits))
    pattern_hits.sort(key=lambda item: item[1], reverse=True)
    pattern_score = min(sum(hit_count for _, hit_count in pattern_hits) / 6.0, 1.0)

    standalone_score = _standalone_score(words)
    score = 0.42 * pattern_score + 0.34 * global_relevance + 0.24 * standalone_score

    reasons = []
    if global_keyword_hits:
        reasons.append("topic context: " + ", ".join(global_keyword_hits[:4]))
    if pattern_hits:
        reasons.append("viral pattern: " + pattern_hits[0][0])
    reasons.append("standalone idea" if standalone_score >= 0.55 else "needs context")
    return min(1.0, score), reasons


def _build_topic_blocks(segments: list[TranscriptSegment]) -> list[TopicBlock]:
    blocks: list[TopicBlock] = []
    start_index = 0
    running_terms = Counter(_content_words(segments[0].text))

    for index in range(1, len(segments)):
        current_terms = Counter(_content_words(segments[index].text))
        previous = segments[index - 1]
        current = segments[index]
        gap = current.start_seconds - previous.end_seconds
        duration = previous.end_seconds - segments[start_index].start_seconds
        similarity = _jaccard(set(running_terms), set(current_terms))
        if duration >= 120 and (gap >= 2.5 or similarity < 0.08):
            blocks.append(_make_topic_block(segments, start_index, index - 1))
            start_index = index
            running_terms = current_terms
            continue
        running_terms.update(current_terms)

    blocks.append(_make_topic_block(segments, start_index, len(segments) - 1))
    return blocks


def _make_topic_block(segments: list[TranscriptSegment], start_index: int, end_index: int) -> TopicBlock:
    selected = segments[start_index : end_index + 1]
    text = " ".join(segment.text for segment in selected)
    keywords = _top_keywords(text, limit=8)
    summary = " ".join(text.split()[:28])
    return TopicBlock(
        start_seconds=selected[0].start_seconds,
        end_seconds=selected[-1].end_seconds,
        keywords=keywords,
        summary=summary,
    )


def _top_keywords(text: str, limit: int) -> list[str]:
    counts = Counter(_content_words(text))
    return [word for word, _ in counts.most_common(limit)]


def _content_words(text: str) -> list[str]:
    return [word for word in _words(text) if word not in STOP_WORDS and len(word) > 2]


def _words(text: str) -> list[str]:
    return [word.strip(".,!?;:()[]{}\"'").lower() for word in text.split() if word.strip()]


def _standalone_score(words: list[str]) -> float:
    opening = set(words[:18])
    closing = set(words[-24:])
    has_setup = bool(opening & {"why", "how", "what", "if", "when", "because", "so", "actually"})
    has_payoff = bool(closing & {"because", "therefore", "simple", "problem", "truth", "means", "important"})
    has_specifics = sum(1 for word in words if len(word) >= 7) >= 4
    return (0.34 if has_setup else 0.0) + (0.33 if has_payoff else 0.0) + (0.33 if has_specifics else 0.0)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = int(seconds % 60)
    return f"{minutes}:{remainder:02}"
