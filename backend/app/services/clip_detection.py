from collections import Counter
from dataclasses import dataclass
from math import sqrt

from backend.app.schemas import ClipCandidate, TranscriptSegment
from backend.app.services.context_analysis import VideoContext, clip_context_features

HOOK_TERMS = {
    "secret",
    "mistake",
    "problem",
    "simple",
    "quick",
    "best",
    "worst",
    "why",
    "how",
    "money",
    "growth",
    "viral",
    "watch",
    "important",
    "never",
}

BOUNDARY_TERMS = {
    "anyway",
    "next",
    "another",
    "moving",
    "finally",
    "overall",
    "basically",
    "question",
}

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


@dataclass(frozen=True)
class ConversationSegment:
    start_index: int
    end_index: int
    start_seconds: float
    end_seconds: float
    text: str
    boundary_reason: str

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


def detect_clips(
    segments: list[TranscriptSegment],
    target_duration_seconds: int = 120,
    clip_count: int = 5,
    min_clip_seconds: int = 45,
    max_clip_seconds: int = 180,
    context: VideoContext | None = None,
) -> list[ClipCandidate]:
    if not segments:
        return []

    max_duration = min(max_clip_seconds, 180)
    conversation_segments = _build_conversation_segments(
        segments,
        min_clip_seconds=min_clip_seconds,
        max_clip_seconds=max_duration,
    )

    candidates = [
        _conversation_to_candidate(segment, target_duration_seconds, max_duration, context)
        for segment in conversation_segments
        if segment.duration >= min_clip_seconds * 0.65
    ]

    if not candidates:
        candidates = _fallback_windows(
            segments,
            target_duration_seconds=target_duration_seconds,
            min_clip_seconds=min_clip_seconds,
            max_clip_seconds=max_duration,
            context=context,
        )

    candidates = [
        _refine_candidate_boundaries(candidate, segments, min_clip_seconds, max_duration)
        for candidate in candidates
    ]
    candidates.sort(key=lambda clip: clip.score, reverse=True)
    selected: list[ClipCandidate] = []
    for candidate in candidates:
        if all(_overlap_ratio(candidate, existing) < 0.25 for existing in selected):
            selected.append(candidate)
        if len(selected) >= clip_count:
            break

    return selected


def _build_conversation_segments(
    segments: list[TranscriptSegment],
    min_clip_seconds: int,
    max_clip_seconds: int,
) -> list[ConversationSegment]:
    conversations: list[ConversationSegment] = []
    start_index = 0
    running_terms = _term_counter(segments[0].text)
    boundary_reason = "conversation start"

    for index in range(1, len(segments)):
        current = segments[index]
        previous = segments[index - 1]
        current_terms = _term_counter(current.text)
        duration = previous.end_seconds - segments[start_index].start_seconds
        gap = current.start_seconds - previous.end_seconds
        similarity = _cosine_similarity(running_terms, current_terms)
        starts_new_topic = _starts_new_topic(current.text)

        should_close = False
        reason = ""
        if duration >= min_clip_seconds and gap >= 1.8:
            should_close = True
            reason = f"{gap:.1f}s pause"
        elif duration >= min_clip_seconds and similarity < 0.08 and starts_new_topic:
            should_close = True
            reason = "topic transition"
        elif duration >= max_clip_seconds:
            should_close = True
            reason = "reached Shorts limit"

        if should_close:
            conversations.append(_make_conversation(segments, start_index, index - 1, boundary_reason))
            start_index = index
            running_terms = current_terms
            boundary_reason = reason
            continue

        running_terms.update(current_terms)

    conversations.append(_make_conversation(segments, start_index, len(segments) - 1, boundary_reason))
    return _split_long_conversations(conversations, segments, max_clip_seconds)


def _split_long_conversations(
    conversations: list[ConversationSegment],
    segments: list[TranscriptSegment],
    max_clip_seconds: int,
) -> list[ConversationSegment]:
    split: list[ConversationSegment] = []
    for conversation in conversations:
        if conversation.duration <= max_clip_seconds:
            split.append(conversation)
            continue

        start_index = conversation.start_index
        while start_index <= conversation.end_index:
            end_index = start_index
            while (
                end_index < conversation.end_index
                and segments[end_index + 1].end_seconds - segments[start_index].start_seconds <= max_clip_seconds
            ):
                end_index += 1
            split.append(_make_conversation(segments, start_index, end_index, "split long conversation"))
            start_index = end_index + 1
    return split


def _make_conversation(
    segments: list[TranscriptSegment],
    start_index: int,
    end_index: int,
    boundary_reason: str,
) -> ConversationSegment:
    selected = segments[start_index : end_index + 1]
    return ConversationSegment(
        start_index=start_index,
        end_index=end_index,
        start_seconds=selected[0].start_seconds,
        end_seconds=selected[-1].end_seconds,
        text=" ".join(segment.text for segment in selected),
        boundary_reason=boundary_reason,
    )


def _conversation_to_candidate(
    segment: ConversationSegment,
    target_duration_seconds: int,
    max_clip_seconds: int,
    context: VideoContext | None,
) -> ClipCandidate:
    score, reason = _score_text_window(
        segment.text,
        duration=segment.duration,
        target_duration_seconds=min(target_duration_seconds, max_clip_seconds),
        context=context,
    )
    complete_bonus = 0.12 if segment.duration <= max_clip_seconds else 0.0
    score = min(1.0, score + complete_bonus)
    return ClipCandidate(
        start_seconds=segment.start_seconds,
        end_seconds=min(segment.end_seconds, segment.start_seconds + max_clip_seconds),
        score=round(score, 3),
        reason=f"complete conversation, {reason}, boundary: {segment.boundary_reason}",
    )


def _fallback_windows(
    segments: list[TranscriptSegment],
    target_duration_seconds: int,
    min_clip_seconds: int,
    max_clip_seconds: int,
    context: VideoContext | None,
) -> list[ClipCandidate]:
    windows: list[ClipCandidate] = []
    for start_index, start_segment in enumerate(segments):
        window_text: list[str] = []
        end = start_segment.end_seconds
        for segment in segments[start_index:]:
            end = segment.end_seconds
            duration = end - start_segment.start_seconds
            if duration > max_clip_seconds:
                break
            window_text.append(segment.text)
            if duration >= min_clip_seconds:
                score, reason = _score_text_window(
                    " ".join(window_text),
                    duration,
                    target_duration_seconds,
                    context=context,
                )
                windows.append(
                    ClipCandidate(
                        start_seconds=start_segment.start_seconds,
                        end_seconds=end,
                        score=score,
                        reason=f"fallback transcript window, {reason}",
                    )
                )
    return windows


def _score_text_window(
    text: str,
    duration: float,
    target_duration_seconds: int,
    context: VideoContext | None = None,
) -> tuple[float, str]:
    words = _words(text)
    hook_hits = sum(1 for word in words if word in HOOK_TERMS)
    density = min(len(words) / max(duration, 1) / 3.0, 1.0)
    duration_fit = max(0.0, 1.0 - abs(duration - target_duration_seconds) / target_duration_seconds)
    hook_score = min(hook_hits / 4.0, 1.0)
    context_score = 0.0
    context_reasons: list[str] = []
    if context is not None:
        context_score, context_reasons = clip_context_features(text, context)
    score = min(1.0, 0.28 * hook_score + 0.24 * duration_fit + 0.16 * density + 0.22 * context_score + 0.1)

    reasons = []
    if hook_hits:
        reasons.append(f"{hook_hits} hook terms")
    reasons.append(f"{int(duration)}s conversation")
    reasons.append("dense exchange" if density > 0.55 else "clear exchange")
    reasons.extend(context_reasons[:2])
    return round(score, 3), ", ".join(reasons)


def _refine_candidate_boundaries(
    candidate: ClipCandidate,
    segments: list[TranscriptSegment],
    min_clip_seconds: int,
    max_clip_seconds: int,
) -> ClipCandidate:
    selected = [
        (index, segment)
        for index, segment in enumerate(segments)
        if segment.end_seconds >= candidate.start_seconds and segment.start_seconds <= candidate.end_seconds
    ]
    if not selected:
        return candidate

    start_position = 0
    while start_position < len(selected) - 1 and _is_weak_opening(selected[start_position][1].text):
        next_start = selected[start_position + 1][1].start_seconds
        if candidate.end_seconds - next_start < min_clip_seconds:
            break
        start_position += 1

    end_position = len(selected) - 1
    while end_position > start_position and _is_weak_ending(selected[end_position][1].text):
        previous_end = selected[end_position - 1][1].end_seconds
        if previous_end - selected[start_position][1].start_seconds < min_clip_seconds:
            break
        end_position -= 1

    start_index = selected[start_position][0]
    end_index = selected[end_position][0]

    if start_index > 0 and _is_context_setup(segments[start_index].text):
        previous = segments[start_index - 1]
        if segments[end_index].end_seconds - previous.start_seconds <= max_clip_seconds:
            start_index -= 1

    if end_index < len(segments) - 1 and _needs_payoff(segments[end_index].text):
        next_segment = segments[end_index + 1]
        if next_segment.end_seconds - segments[start_index].start_seconds <= max_clip_seconds:
            end_index += 1

    start_seconds = segments[start_index].start_seconds
    end_seconds = segments[end_index].end_seconds
    if start_seconds == candidate.start_seconds and end_seconds == candidate.end_seconds:
        return candidate

    return ClipCandidate(
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        score=candidate.score,
        reason=f"{candidate.reason}, refined boundaries",
    )


def _is_weak_opening(text: str) -> bool:
    words = _words(text)
    if not words:
        return True
    weak_openers = {"yeah", "yes", "no", "okay", "right", "like", "um", "uh", "well"}
    return len(words) <= 4 and words[0] in weak_openers


def _is_weak_ending(text: str) -> bool:
    words = _words(text)
    if not words:
        return True
    return len(words) <= 3 and words[-1] in {"yeah", "right", "okay", "so", "and", "but"}


def _is_context_setup(text: str) -> bool:
    words = set(_words(text)[:12])
    return bool(words & {"because", "if", "when", "why", "how", "what"})


def _needs_payoff(text: str) -> bool:
    words = set(_words(text)[-10:])
    return bool(words & {"because", "so", "therefore", "means", "then"})


def _term_counter(text: str) -> Counter[str]:
    return Counter(word for word in _words(text) if word not in STOP_WORDS and len(word) > 2)


def _words(text: str) -> list[str]:
    return [word.strip(".,!?;:()[]{}\"'").lower() for word in text.split() if word.strip()]


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[word] * right[word] for word in shared)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _starts_new_topic(text: str) -> bool:
    words = set(_words(text)[:8])
    return bool(words & BOUNDARY_TERMS)


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    overlap = max(0.0, min(a.end_seconds, b.end_seconds) - max(a.start_seconds, b.start_seconds))
    shortest = max(1.0, min(a.end_seconds - a.start_seconds, b.end_seconds - b.start_seconds))
    return overlap / shortest
