import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


TARGET_ASPECT_RATIO = 9 / 16
MIN_TRACK_SAMPLES = 2


@dataclass(frozen=True)
class CropWindow:
    width: int
    height: int
    x: int
    y: int


@dataclass(frozen=True)
class SpeakerTarget:
    center_x: float
    center_y: float
    face_width: float
    face_height: float
    mouth_motion_confidence: float


@dataclass(frozen=True)
class RenderLayout:
    mode: str
    primary_crop: CropWindow | None
    secondary_crop: CropWindow | None = None


@dataclass
class FaceObservation:
    timestamp: float
    x: int
    y: int
    width: int
    height: int
    center_x: float
    center_y: float
    area: int
    lower_face_gray: object


@dataclass
class FaceTrack:
    observations: list[FaceObservation]
    motion_score: float = 0.0

    @property
    def latest(self) -> FaceObservation:
        return self.observations[-1]

    @property
    def sample_count(self) -> int:
        return len(self.observations)

    @property
    def average_area(self) -> float:
        return sum(observation.area for observation in self.observations) / self.sample_count

    @property
    def center(self) -> tuple[float, float]:
        total_weight = sum(observation.area for observation in self.observations)
        center_x = sum(observation.center_x * observation.area for observation in self.observations) / total_weight
        center_y = sum(observation.center_y * observation.area for observation in self.observations) / total_weight
        return center_x, center_y

    @property
    def average_face_size(self) -> tuple[float, float]:
        return (
            sum(observation.width for observation in self.observations) / self.sample_count,
            sum(observation.height for observation in self.observations) / self.sample_count,
        )


def detect_speaker_crop(
    video_path: str | Path,
    start_seconds: float,
    end_seconds: float,
) -> CropWindow | None:
    dimensions = _probe_dimensions(video_path)
    if dimensions is None:
        return None

    width, height = dimensions
    target = _detect_speaker_target(video_path, start_seconds, end_seconds)
    focus_x, focus_y = _body_aware_focus(target, width, height) if target else (width / 2, height / 2)

    source_aspect = width / height
    if source_aspect > TARGET_ASPECT_RATIO:
        crop_height = height
        crop_width = int(round(height * TARGET_ASPECT_RATIO))
        crop_x = _clamp_int(round(focus_x - crop_width / 2), 0, width - crop_width)
        return CropWindow(width=crop_width, height=crop_height, x=crop_x, y=0)

    crop_width = width
    crop_height = int(round(width / TARGET_ASPECT_RATIO))
    crop_y = _clamp_int(round(focus_y - crop_height / 2), 0, height - crop_height)
    return CropWindow(width=crop_width, height=crop_height, x=0, y=crop_y)


def detect_render_layout(
    video_path: str | Path,
    start_seconds: float,
    end_seconds: float,
) -> RenderLayout:
    dimensions = _probe_dimensions(video_path)
    if dimensions is None:
        return RenderLayout(mode="fallback_center", primary_crop=None)

    width, height = dimensions
    targets = _detect_speaker_targets(video_path, start_seconds, end_seconds)
    split_pair = _best_split_screen_pair(targets, width, height)
    if split_pair is not None:
        left, right = split_pair
        return RenderLayout(
            mode="two_person_split",
            primary_crop=_target_to_half_crop(left, width, height),
            secondary_crop=_target_to_half_crop(right, width, height),
        )

    primary_target = _choose_primary_target(targets, width)
    primary = _target_to_vertical_crop(primary_target, width, height) if primary_target else None
    return RenderLayout(mode="single_speaker", primary_crop=primary)


def _best_split_screen_pair(
    targets: list[SpeakerTarget],
    frame_width: int,
    frame_height: int,
) -> tuple[SpeakerTarget, SpeakerTarget] | None:
    if not targets:
        return None

    largest_face_width = max(target.face_width for target in targets)
    best_pair = None
    best_score = 0.0
    for left_index, left_target in enumerate(targets):
        for right_target in targets[left_index + 1 :]:
            left, right = sorted((left_target, right_target), key=lambda target: target.center_x)
            if not _should_use_split_screen(left, right, frame_width, frame_height, largest_face_width):
                continue
            horizontal_distance = abs(right.center_x - left.center_x)
            combined_face_width = left.face_width + right.face_width
            score = combined_face_width * 0.7 + horizontal_distance * 0.3
            if score > best_score:
                best_score = score
                best_pair = (left, right)
    return best_pair


def _choose_primary_target(targets: list[SpeakerTarget], frame_width: int) -> SpeakerTarget | None:
    if not targets:
        return None

    cluster_radius = frame_width * 0.08
    best_cluster: list[SpeakerTarget] = []
    best_score = 0.0
    for target in targets:
        cluster = [
            candidate
            for candidate in targets
            if abs(candidate.center_x - target.center_x) <= cluster_radius
            and abs(candidate.center_y - target.center_y) <= cluster_radius
        ]
        average_confidence = sum(candidate.mouth_motion_confidence for candidate in cluster) / len(cluster)
        average_face_width = sum(candidate.face_width for candidate in cluster) / len(cluster)
        score = len(cluster) * 0.45 + average_confidence * 0.35 + min(average_face_width / frame_width, 0.2)
        if score > best_score:
            best_score = score
            best_cluster = cluster

    if len(best_cluster) <= 1:
        return targets[0]

    weights = [target.face_width * max(target.mouth_motion_confidence, 0.2) for target in best_cluster]
    total_weight = sum(weights)
    return SpeakerTarget(
        center_x=sum(target.center_x * weight for target, weight in zip(best_cluster, weights)) / total_weight,
        center_y=sum(target.center_y * weight for target, weight in zip(best_cluster, weights)) / total_weight,
        face_width=sum(target.face_width for target in best_cluster) / len(best_cluster),
        face_height=sum(target.face_height for target in best_cluster) / len(best_cluster),
        mouth_motion_confidence=sum(target.mouth_motion_confidence for target in best_cluster) / len(best_cluster),
    )


def _probe_dimensions(video_path: str | Path) -> tuple[int, int] | None:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    if not streams:
        return None
    width = streams[0].get("width")
    height = streams[0].get("height")
    if not width or not height:
        return None
    return int(width), int(height)


def _detect_speaker_target(
    video_path: str | Path,
    start_seconds: float,
    end_seconds: float,
) -> SpeakerTarget | None:
    try:
        import cv2
    except ImportError:
        return None

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None

    tracks: list[FaceTrack] = []
    duration = max(0.1, end_seconds - start_seconds)
    sample_count = min(24, max(8, int(duration * 1.5)))
    try:
        for index in range(sample_count):
            timestamp = start_seconds + duration * (index + 0.5) / sample_count
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(48, 48),
            )
            if len(faces) == 0:
                continue
            observations = [
                _create_observation(cv2, gray, timestamp, face)
                for face in sorted(faces, key=lambda face: face[2] * face[3], reverse=True)[:4]
            ]
            _assign_observations_to_tracks(cv2, tracks, observations)
    finally:
        capture.release()

    if not tracks:
        return None

    best_track = max(tracks, key=lambda track: _track_score(track, sample_count))
    if best_track.sample_count < MIN_TRACK_SAMPLES:
        return None
    center_x, center_y = best_track.center
    face_width, face_height = best_track.average_face_size
    return SpeakerTarget(
        center_x=center_x,
        center_y=center_y,
        face_width=face_width,
        face_height=face_height,
        mouth_motion_confidence=_mouth_motion_confidence(best_track),
    )


def _detect_speaker_targets(
    video_path: str | Path,
    start_seconds: float,
    end_seconds: float,
) -> list[SpeakerTarget]:
    try:
        import cv2
    except ImportError:
        return []

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        return []

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []

    tracks: list[FaceTrack] = []
    duration = max(0.1, end_seconds - start_seconds)
    sample_count = min(24, max(8, int(duration * 1.5)))
    try:
        for index in range(sample_count):
            timestamp = start_seconds + duration * (index + 0.5) / sample_count
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(48, 48),
            )
            observations = [
                _create_observation(cv2, gray, timestamp, face)
                for face in sorted(faces, key=lambda face: face[2] * face[3], reverse=True)[:4]
            ]
            _assign_observations_to_tracks(cv2, tracks, observations)
    finally:
        capture.release()

    ranked_tracks = sorted(
        [track for track in tracks if track.sample_count >= MIN_TRACK_SAMPLES],
        key=lambda track: _track_score(track, sample_count),
        reverse=True,
    )
    targets: list[SpeakerTarget] = []
    for track in ranked_tracks[:3]:
        center_x, center_y = track.center
        face_width, face_height = track.average_face_size
        targets.append(
            SpeakerTarget(
                center_x=center_x,
                center_y=center_y,
                face_width=face_width,
                face_height=face_height,
                mouth_motion_confidence=_mouth_motion_confidence(track),
            )
        )
    return targets


def _create_observation(cv2, gray, timestamp: float, face) -> FaceObservation:
    x, y, width, height = [int(value) for value in face]
    lower_y = y + int(height * 0.48)
    lower_face = gray[lower_y : y + height, x : x + width]
    lower_face_gray = cv2.resize(lower_face, (64, 32)) if lower_face.size else None
    return FaceObservation(
        timestamp=timestamp,
        x=x,
        y=y,
        width=width,
        height=height,
        center_x=x + width / 2,
        center_y=y + height / 2,
        area=width * height,
        lower_face_gray=lower_face_gray,
    )


def _assign_observations_to_tracks(cv2, tracks: list[FaceTrack], observations: list[FaceObservation]) -> None:
    assigned_tracks: set[int] = set()
    for observation in observations:
        match_index = _nearest_track_index(tracks, observation, assigned_tracks)
        if match_index is None:
            tracks.append(FaceTrack(observations=[observation]))
            assigned_tracks.add(len(tracks) - 1)
            continue

        track = tracks[match_index]
        previous = track.latest
        track.motion_score += _lower_face_motion(cv2, previous, observation)
        track.observations.append(observation)
        assigned_tracks.add(match_index)


def _nearest_track_index(
    tracks: list[FaceTrack],
    observation: FaceObservation,
    assigned_tracks: set[int],
) -> int | None:
    best_index = None
    best_distance = float("inf")
    for index, track in enumerate(tracks):
        if index in assigned_tracks:
            continue
        latest = track.latest
        max_face_size = max(latest.width, latest.height, observation.width, observation.height)
        distance = ((latest.center_x - observation.center_x) ** 2 + (latest.center_y - observation.center_y) ** 2) ** 0.5
        if distance < max_face_size * 0.75 and distance < best_distance:
            best_distance = distance
            best_index = index
    return best_index


def _lower_face_motion(cv2, previous: FaceObservation, current: FaceObservation) -> float:
    if previous.lower_face_gray is None or current.lower_face_gray is None:
        return 0.0
    diff = cv2.absdiff(previous.lower_face_gray, current.lower_face_gray)
    return float(diff.mean())


def _track_score(track: FaceTrack, sample_count: int) -> float:
    persistence = track.sample_count / sample_count
    area_score = min(track.average_area / 25_000, 1.0)
    motion_score = min((track.motion_score / max(track.sample_count - 1, 1)) / 18.0, 1.0)
    return 0.55 * motion_score + 0.3 * persistence + 0.15 * area_score


def _mouth_motion_confidence(track: FaceTrack) -> float:
    if track.sample_count <= 1:
        return 0.0
    average_motion = track.motion_score / (track.sample_count - 1)
    return min(1.0, average_motion / 18.0)


def _body_aware_focus(target: SpeakerTarget, frame_width: int, frame_height: int) -> tuple[float, float]:
    # Aim below the face center so the final vertical crop includes shoulders/chest,
    # not just a perfectly centered face. Higher mouth-motion confidence keeps the
    # speaker more centered; lower confidence gives more neutral body framing.
    torso_offset = target.face_height * (1.25 - 0.35 * target.mouth_motion_confidence)
    focus_y = target.center_y + torso_offset
    focus_x = target.center_x
    return (
        max(0.0, min(frame_width, focus_x)),
        max(0.0, min(frame_height, focus_y)),
    )


def _target_to_vertical_crop(target: SpeakerTarget, frame_width: int, frame_height: int) -> CropWindow:
    focus_x, focus_y = _body_aware_focus(target, frame_width, frame_height)
    source_aspect = frame_width / frame_height
    if source_aspect > TARGET_ASPECT_RATIO:
        crop_height = frame_height
        crop_width = int(round(frame_height * TARGET_ASPECT_RATIO))
        crop_x = _clamp_int(round(focus_x - crop_width / 2), 0, frame_width - crop_width)
        return CropWindow(width=crop_width, height=crop_height, x=crop_x, y=0)

    crop_width = frame_width
    crop_height = int(round(frame_width / TARGET_ASPECT_RATIO))
    crop_y = _clamp_int(round(focus_y - crop_height / 2), 0, frame_height - crop_height)
    return CropWindow(width=crop_width, height=crop_height, x=0, y=crop_y)


def _target_to_half_crop(target: SpeakerTarget, frame_width: int, frame_height: int) -> CropWindow:
    crop_width = max(1, min(frame_width, int(round(target.face_width * 4.4))))
    crop_height = max(1, min(frame_height, int(round(crop_width * 8 / 9))))
    focus_x, focus_y = _body_aware_focus(target, frame_width, frame_height)
    crop_x = _clamp_int(round(focus_x - crop_width / 2), 0, frame_width - crop_width)
    crop_y = _clamp_int(round(focus_y - crop_height * 0.45), 0, frame_height - crop_height)
    return CropWindow(width=crop_width, height=crop_height, x=crop_x, y=crop_y)


def _should_use_split_screen(
    left: SpeakerTarget,
    right: SpeakerTarget,
    frame_width: int,
    frame_height: int,
    largest_face_width: float,
) -> bool:
    if min(left.mouth_motion_confidence, right.mouth_motion_confidence) < 0.35:
        return False
    if min(left.face_width, right.face_width) < frame_width * 0.06:
        return False
    if min(left.face_width, right.face_width) < largest_face_width * 0.55:
        return False
    horizontal_distance = abs(right.center_x - left.center_x)
    minimum_distance = frame_width * 0.34
    combined_face_width = left.face_width + right.face_width
    single_crop_width = int(round(frame_height * TARGET_ASPECT_RATIO))
    would_not_fit_single_crop = horizontal_distance + combined_face_width * 0.9 > single_crop_width
    return horizontal_distance >= minimum_distance and would_not_fit_single_crop


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
