from __future__ import annotations
import copy
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Callable, Any
MICROSECONDS = 1_000_000
SUPPORTED_VIDEO_TRACK_TYPES = {"video"}
VALID_DISTRIBUTION_MODES = {"all", "alternate", "random", "random_no_repeat"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".webm", ".mpeg", ".mpg"}
TEXT_TRACK_TYPES = {"text", "subtitle", "captions", "caption"}
AUDIO_TRACK_TYPES = {"audio", "music", "voice"}
DEFAULT_FPS = 25.0
IO_RETRY_ATTEMPTS = 12
IO_RETRY_DELAY_SEC = 0.35
FILE_SETTLE_TIMEOUT_SEC = 4.0
FILE_SETTLE_INTERVAL_SEC = 0.2
FILE_SETTLE_STABLE_TICKS = 3

class DraftEngineError(Exception):
    pass
def _frame_us(fps: float = DEFAULT_FPS) -> int:
    fps = fps or DEFAULT_FPS
    if fps <= 0:
        fps = DEFAULT_FPS
    return max(1, int(round(MICROSECONDS / fps)))

def _snap_time_us(value: int, frame_us: int, mode: str = "nearest") -> int:
    value = _safe_int(value, 0)
    if frame_us <= 1:
        return value
    if mode == "floor":
        return (value // frame_us) * frame_us
    if mode == "ceil":
        return ((value + frame_us - 1) // frame_us) * frame_us
    return int(round(value / frame_us)) * frame_us

def _normalize_frame_counts(boundaries: list[int], total_duration_us: int, frame_us: int) -> list[int]:
    total_frames = max(1, int(round(total_duration_us / frame_us)))
    frames = []
    prev = 0
    for i, b in enumerate(boundaries):
        if i == 0:
            f = 0
        elif i == len(boundaries) - 1:
            f = total_frames
        else:
            f = int(round((b - boundaries[0]) / frame_us))
            f = max(prev, min(total_frames, f))
        frames.append(f)
        prev = f
    if frames[-1] != total_frames:
        frames[-1] = total_frames
    return frames

def _contiguous_frame_source_ranges(segments: list[dict], frame_us: int) -> list[tuple[int,int]]:
    if not segments:
        return []
    first_sr = segments[0].get("source_timerange") or {}
    first_start = _safe_int(first_sr.get("start", 0))
    first_start = _snap_time_us(first_start, frame_us, "floor")
    out=[]
    cursor = first_start
    for i, seg in enumerate(segments):
        sr = seg.get("source_timerange") or {}
        dur = _safe_int(sr.get("duration", 0)) or _safe_int((seg.get("target_timerange") or {}).get("duration", 0))
        frames = max(1, int(round(dur / frame_us)))
        dur_us = frames * frame_us
        out.append((cursor, dur_us))
        cursor += dur_us
    return out



def _ensure_speed_material(data: Dict[str, Any], segment: Dict[str, Any], speed: float) -> str:
    """Attach a *unique* speed material to this segment so CapCut UI reads the exact clip speed.

    Split clips often inherit the same speed material ref from the source clip. If we keep reusing that
    shared ref, later updates overwrite earlier clips and CapCut ends up showing 1.0x or the wrong speed.
    So for each written segment we drop inherited speed refs and prepend a fresh speed material id.
    """
    materials = data.setdefault("materials", {})
    speeds = materials.setdefault("speeds", [])
    if not isinstance(speeds, list):
        materials["speeds"] = []
        speeds = materials["speeds"]

    refs = segment.get("extra_material_refs")
    if not isinstance(refs, list):
        refs = []

    speed_ids = {str(item.get("id")) for item in speeds if isinstance(item, dict) and item.get("id")}
    refs = [ref for ref in refs if not (isinstance(ref, str) and ref in speed_ids)]

    speed_ref_id = new_uuid()
    speeds.append({
        "curve_speed": None,
        "id": speed_ref_id,
        "mode": 0,
        "speed": float(speed),
        "type": "speed",
    })

    refs.insert(0, speed_ref_id)
    segment["extra_material_refs"] = refs
    segment["speed"] = float(speed)
    return speed_ref_id

def new_uuid() -> str:
    return str(uuid.uuid4()).upper()
def _point(time_offset: int, value: float) -> Dict[str, Any]:
    return {
        "curveType": "Line",
        "graphID": "",
        "id": new_uuid(),
        "left_control": {"x": 0.0, "y": 0.0},
        "right_control": {"x": 0.0, "y": 0.0},
        "string_value": "",
        "time_offset": int(time_offset),
        "values": [float(value)],
    }
def _group(property_type: str, points: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "material_id": "",
        "property_type": property_type,
        "keyframe_list": points,
    }
def build_zoom_in(duration_us: int, start_scale: float, end_scale: float) -> List[Dict[str, Any]]:
    return [
        _group(
            "KFTypeScaleX",
            [
                _point(0, start_scale),
                _point(duration_us, end_scale),
            ],
        )
    ]
def build_zoom_out(duration_us: int, start_scale: float, end_scale: float) -> List[Dict[str, Any]]:
    return build_zoom_in(duration_us, start_scale, end_scale)
def build_zoom_move_x(duration_us: int, scale: float, x1: float, x2: float) -> List[Dict[str, Any]]:
    return [
        _group("KFTypeScaleX", [_point(0, scale), _point(duration_us, scale)]),
        _group("KFTypePositionX", [_point(0, x1), _point(duration_us, x2)]),
        _group("KFTypePositionY", [_point(0, 0.0), _point(duration_us, 0.0)]),
    ]
def build_zoom_move_y(duration_us: int, scale: float, y1: float, y2: float) -> List[Dict[str, Any]]:
    return [
        _group("KFTypeScaleX", [_point(0, scale), _point(duration_us, scale)]),
        _group("KFTypePositionX", [_point(0, 0.0), _point(duration_us, 0.0)]),
        _group("KFTypePositionY", [_point(0, y1), _point(duration_us, y2)]),
    ]
def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))


def _wait_for_file_settle(path: Path) -> None:
    deadline = time.monotonic() + FILE_SETTLE_TIMEOUT_SEC
    last_sig = None
    stable_ticks = 0
    while time.monotonic() < deadline:
        sig = _file_signature(path)
        if sig is None:
            last_sig = None
            stable_ticks = 0
            time.sleep(FILE_SETTLE_INTERVAL_SEC)
            continue
        if sig == last_sig and sig[0] > 0:
            stable_ticks += 1
            if stable_ticks >= FILE_SETTLE_STABLE_TICKS:
                return
        else:
            last_sig = sig
            stable_ticks = 1 if sig[0] > 0 else 0
        time.sleep(FILE_SETTLE_INTERVAL_SEC)


def _is_tracks_ready(data: Dict[str, Any]) -> bool:
    tracks = data.get("tracks")
    return isinstance(tracks, list) and bool(tracks)


def load_json(path: Path, *, retries: int = IO_RETRY_ATTEMPTS, retry_delay: float = IO_RETRY_DELAY_SEC) -> Dict[str, Any]:
    last_exc: Exception | None = None
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        if path.exists():
            _wait_for_file_settle(path)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise DraftEngineError(f"Cấu trúc JSON không hợp lệ trong file {path}")
            return data
        except (json.JSONDecodeError, OSError, PermissionError, DraftEngineError) as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            time.sleep(retry_delay)
    raise DraftEngineError(
        f"Không đọc ổn định được file {path}. Hãy đợi CapCut lưu xong hẳn rồi thử lại. Chi tiết: {last_exc}"
    ) from last_exc


def load_draft_json(
    path: Path,
    *,
    require_tracks: bool = False,
    retries: int = IO_RETRY_ATTEMPTS,
    retry_delay: float = IO_RETRY_DELAY_SEC,
) -> Dict[str, Any]:
    last_data: Dict[str, Any] | None = None
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        data = load_json(path, retries=1, retry_delay=retry_delay)
        last_data = data
        if not require_tracks or _is_tracks_ready(data):
            return data
        if attempt >= attempts - 1:
            break
        time.sleep(retry_delay)
    if require_tracks:
        raise DraftEngineError(
            f"Project {path.parent.name} vừa đóng nhưng timeline vẫn chưa ổn định (tracks còn rỗng). "
            "Hãy chờ 2-5 giây sau khi tắt CapCut rồi thử lại."
        )
    return last_data or {}
def _legacy_save_json(path: Path, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
    try:
        tmp_path.replace(path)
        return
    except (PermissionError, OSError):
        pass
    try:
        if path.exists():
            os.chmod(path, stat.S_IWRITE)
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
    except Exception as exc:
        raise DraftEngineError(
            f"Không ghi được file {path}. Hãy đóng CapCut rồi thử lại. Chi tiết: {exc}"
        ) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
def _legacy_backup_draft(draft_path: Path) -> Path:
    backup_path = draft_path.with_suffix(".json.bak")
    shutil.copy2(draft_path, backup_path)
    return backup_path


def save_json(path: Path, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    last_exc: Exception | None = None
    for attempt in range(IO_RETRY_ATTEMPTS):
        try:
            if path.exists():
                _wait_for_file_settle(path)
            with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            tmp_path.replace(path)
            return
        except (PermissionError, OSError) as exc:
            last_exc = exc
        try:
            if path.exists():
                os.chmod(path, stat.S_IWRITE)
            with path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(payload)
            return
        except Exception as exc:
            last_exc = exc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        if attempt < IO_RETRY_ATTEMPTS - 1:
            time.sleep(IO_RETRY_DELAY_SEC)
    raise DraftEngineError(
        f"Không ghi được file {path}. Có thể CapCut hoặc tiến trình đồng bộ file vẫn đang giữ file này. "
        f"Hãy đợi vài giây rồi thử lại. Chi tiết: {last_exc}"
    ) from last_exc


def backup_draft(draft_path: Path) -> Path:
    backup_path = draft_path.with_suffix(".json.bak")
    last_exc: Exception | None = None
    for attempt in range(IO_RETRY_ATTEMPTS):
        try:
            if draft_path.exists():
                _wait_for_file_settle(draft_path)
            shutil.copy2(draft_path, backup_path)
            return backup_path
        except (PermissionError, OSError) as exc:
            last_exc = exc
            if attempt < IO_RETRY_ATTEMPTS - 1:
                time.sleep(IO_RETRY_DELAY_SEC)
    raise DraftEngineError(
        f"Không tạo được backup cho file {draft_path}. Chi tiết: {last_exc}"
    ) from last_exc


def normalize_project_metadata(project_dir: Path, logger: Callable[[str], None] | None = None) -> None:
    meta_path = project_dir / "draft_meta_info.json"
    if not meta_path.exists():
        return
    log = logger or (lambda _msg: None)
    try:
        data = load_json(meta_path, retries=2, retry_delay=0.1)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    expected_fold = project_dir.as_posix()
    expected_root = project_dir.parent.as_posix()
    changed = False
    if data.get("draft_fold_path") != expected_fold:
        data["draft_fold_path"] = expected_fold
        changed = True
    if data.get("draft_root_path") != expected_root:
        data["draft_root_path"] = expected_root
        changed = True
    if isinstance(data.get("draft_name"), str) and data.get("draft_name") != project_dir.name:
        data["draft_name"] = project_dir.name
        changed = True
    if not changed:
        return
    save_json(meta_path, data)
    log(f"  🛠️ Đã chuẩn hóa metadata project: {project_dir.name}")


def _debug_snapshot_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "_debug_step1_snapshots"
    return Path(__file__).resolve().parent.parent / "_debug_step1_snapshots"


def write_debug_snapshot(project_dir: Path, stage: str, data: Dict[str, Any]) -> Path | None:
    try:
        snap_dir = _debug_snapshot_dir()
        snap_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_name = "".join(ch if ch.isalnum() or ch in (" ", "-", "_", "(", ")") else "_" for ch in project_dir.name).strip()
        if not safe_name:
            safe_name = "project"
        out_path = snap_dir / f"{safe_name}_{stage}_{stamp}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path
    except Exception:
        return None


def resolve_project_draft_paths(project_dir: Path) -> tuple[Path, List[Path]]:
    root_draft = project_dir / "draft_content.json"
    mirrors: List[Path] = []
    timeline_project = project_dir / "Timelines" / "project.json"
    primary = root_draft
    if timeline_project.exists():
        try:
            data = load_json(timeline_project, retries=2, retry_delay=0.1)
            main_timeline_id = str(data.get("main_timeline_id", "")).strip()
            if main_timeline_id:
                timeline_draft = project_dir / "Timelines" / main_timeline_id / "draft_content.json"
                if timeline_draft.exists():
                    primary = timeline_draft
        except Exception:
            pass
    if primary != root_draft:
        mirrors.append(root_draft)
    return primary, mirrors


def backup_project_drafts(primary: Path, mirrors: List[Path]) -> None:
    seen: set[str] = set()
    for path in [primary, *mirrors]:
        key = str(path).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        backup_draft(path)


def save_project_drafts(primary: Path, mirrors: List[Path], data: Dict[str, Any]) -> None:
    save_json(primary, data)
    for mirror in mirrors:
        save_json(mirror, data)
def get_video_track(data: Dict[str, Any]) -> Dict[str, Any]:
    tracks = data.get("tracks", [])
    for track in tracks:
        if track.get("type") in SUPPORTED_VIDEO_TRACK_TYPES:
            return track
    raise DraftEngineError("Không tìm thấy video track trong draft_content.json")
def iter_video_segments(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    track = get_video_track(data)
    segments = track.get("segments", [])
    if not isinstance(segments, list):
        raise DraftEngineError("Cấu trúc video track không hợp lệ: segments không phải list")
    return segments
def get_project_fps(data: Dict[str, Any]) -> float:
    """Lấy FPS thực tế từ draft_content.json, mặc định trả về DEFAULT_FPS nếu không có."""
    try:
        fps = data.get("fps")
        if isinstance(fps, (int, float)) and fps > 0:
            return float(fps)
        materials = data.get("materials", {}).get("video", [])
        if isinstance(materials, list):
            for mat in materials:
                if isinstance(mat, dict):
                    mat_fps = mat.get("fps")
                    if isinstance(mat_fps, (int, float)) and mat_fps > 0:
                        return float(mat_fps)
    except Exception:
        pass
    return DEFAULT_FPS

EFFECT_BUILDERS = {
    "zoom_in": lambda duration_us, params: build_zoom_in(duration_us, params["start_scale"], params["end_scale"]),
    "zoom_out": lambda duration_us, params: build_zoom_out(duration_us, params["start_scale"], params["end_scale"]),
    "zoom_move_x": lambda duration_us, params: build_zoom_move_x(duration_us, params["scale"], params["x1"], params["x2"]),
    "zoom_move_y": lambda duration_us, params: build_zoom_move_y(duration_us, params["scale"], params["y1"], params["y2"]),
}
def _build_material_lookup(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    materials = data.get("materials", {})
    if isinstance(materials, dict):
        for value in materials.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("id"):
                        lookup[str(item.get("id"))] = item
    return lookup
def _extract_path_from_material(material: Dict[str, Any]) -> str:
    for key in ("path", "file_path", "source_path", "filepath", "local_material_file_path", "material_url", "extra_info"):
        value = material.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
def _segment_material(segment: Dict[str, Any], lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    for key in ("material_id", "source_material_id", "video_material_id"):
        mid = segment.get(key)
        if mid and str(mid) in lookup:
            return lookup[str(mid)]
    refs = segment.get("extra_material_refs") or []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, str) and ref in lookup:
                return lookup[ref]
    return None
def is_image_segment(segment: Dict[str, Any], material_lookup: Dict[str, Dict[str, Any]]) -> bool:
    for key in ("media_type", "source_type", "clip_type", "type"):
        value = str(segment.get(key, "")).lower()
        if value in {"image", "photo", "picture", "img", "photo_segment"}:
            return True
        if value in {"video", "video_segment", "movie"}:
            return False
    material = _segment_material(segment, material_lookup)
    if material:
        for key in ("media_type", "type", "category"):
            value = str(material.get(key, "")).lower()
            if value in {"image", "photo", "picture", "img"}:
                return True
            if value in {"video", "movie", "clip"}:
                return False
        path = _extract_path_from_material(material)
        if path:
            suffix = Path(path).suffix.lower()
            if suffix in IMAGE_EXTS:
                return True
            if suffix in VIDEO_EXTS:
                return False
    return False
def _pick_effects_for_segment(effects: List[Dict[str, Any]], distribution_mode: str, segment_index: int, previous_effect_key: str | None = None) -> List[Dict[str, Any]]:
    if distribution_mode == "all":
        return effects
    if distribution_mode == "alternate":
        return [effects[segment_index % len(effects)]]
    if distribution_mode == "random":
        return [random.choice(effects)]
    if distribution_mode == "random_no_repeat":
        if len(effects) == 1:
            return [effects[0]]
        candidates = [effect for effect in effects if effect.get("key") != previous_effect_key]
        if not candidates:
            candidates = effects
        return [random.choice(candidates)]
    raise DraftEngineError(f"distribution_mode không hợp lệ: {distribution_mode}")
def apply_keyframes_to_project(
    project_dir: Path,
    effects: List[Dict[str, Any]],
    distribution_mode: str = "all",
    clear_existing: bool = True,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
    only_images: bool = False,
) -> Dict[str, Any]:
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"Không tìm thấy file: {draft_path}")
    if not effects:
        raise DraftEngineError("Danh sách effects đang trống")
    if distribution_mode not in VALID_DISTRIBUTION_MODES:
        raise DraftEngineError(f"distribution_mode không hợp lệ: {distribution_mode}")
    log = logger or (lambda _msg: None)
    if backup:
        backup_project_drafts(draft_path, mirror_paths)
        log("  💾 Đã tạo file backup draft_content.json.bak")
    data = load_draft_json(draft_path, require_tracks=True)
    segments = iter_video_segments(data)
    if not segments:
        raise DraftEngineError("Project không có video segment nào để thêm keyframe")
    material_lookup = _build_material_lookup(data)
    total_injected = 0
    segments_touched = 0
    effect_counter: Dict[str, int] = {}
    previous_effect_key: str | None = None
    skipped_non_image = 0
    for idx, segment in enumerate(segments, start=1):
        target_timerange = segment.get("target_timerange", {})
        duration_us = int(target_timerange.get("duration", 0) or 0)
        if duration_us <= 0:
            log(f"  ⚠️ Bỏ qua segment {idx}: duration không hợp lệ")
            continue
        if only_images and not is_image_segment(segment, material_lookup):
            skipped_non_image += 1
            log(f"  ⏭️ Bỏ qua segment {idx}: không phải ảnh")
            continue
        if clear_existing:
            segment["common_keyframes"] = []
        existing = segment.setdefault("common_keyframes", [])
        picked_effects = _pick_effects_for_segment(effects, distribution_mode, idx - 1, previous_effect_key)
        chosen_labels = []
        for effect in picked_effects:
            effect_key = effect["key"]
            params = effect["params"]
            builder = EFFECT_BUILDERS[effect_key]
            groups = builder(duration_us, params)
            existing.extend(groups)
            total_injected += len(groups)
            effect_counter[effect_key] = effect_counter.get(effect_key, 0) + 1
            chosen_labels.append(effect.get("label", effect_key))
            previous_effect_key = effect_key
        segments_touched += 1
        log(f"  • Segment {idx}: {', '.join(chosen_labels)}")
    save_project_drafts(draft_path, mirror_paths, data)
    return {
        "segments_updated": segments_touched,
        "groups_added": total_injected,
        "draft_path": str(draft_path),
        "effect_counter": effect_counter,
        "distribution_mode": distribution_mode,
        "only_images": only_images,
        "skipped_non_image": skipped_non_image,
    }
def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
def _mp3_duration_us(path: Path) -> int:
    data = path.read_bytes()
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = 0
        for b in data[6:10]:
            size = (size << 7) | (b & 0x7F)
        pos = 10 + size
    bitrates = {
        (3, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
        (2, 3): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0],
        (3, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0],
        (2, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
        (0, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
        (0, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
    }
    sample_rates = {
        3: [44100, 48000, 32000, 0],
        2: [22050, 24000, 16000, 0],
        0: [11025, 12000, 8000, 0],
    }
    total_seconds = 0.0
    frames = 0
    while pos + 4 <= len(data):
        if data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
            pos += 1
            continue
        header = int.from_bytes(data[pos:pos + 4], "big")
        version = (header >> 19) & 0x3
        layer = (header >> 17) & 0x3
        bitrate_idx = (header >> 12) & 0xF
        sample_idx = (header >> 10) & 0x3
        padding = (header >> 9) & 0x1
        if version == 1 or layer == 0:
            pos += 1
            continue
        bitrate = (bitrates.get((version, layer)) or [0] * 16)[bitrate_idx] * 1000
        sample_rate = (sample_rates.get(version) or [0] * 4)[sample_idx]
        if bitrate <= 0 or sample_rate <= 0:
            pos += 1
            continue
        if layer == 3:
            samples = 384
            frame_size = int((12 * bitrate / sample_rate + padding) * 4)
        elif layer == 2:
            samples = 1152
            frame_size = int(144 * bitrate / sample_rate + padding)
        else:
            samples = 1152 if version == 3 else 576
            frame_size = int((144 if version == 3 else 72) * bitrate / sample_rate + padding)
        if frame_size <= 0:
            pos += 1
            continue
        total_seconds += samples / sample_rate
        frames += 1
        pos += frame_size
    return int(round(total_seconds * MICROSECONDS)) if frames else 0
def _ffprobe_duration_us(path: Path) -> int:
    app_root = Path(os.environ.get("HHVIETSUB_APP_ROOT", "")).expanduser()
    bundled_ffprobe = app_root / "vendor" / "ffmpeg" / "ffprobe.exe"
    ffprobe = str(bundled_ffprobe) if bundled_ffprobe.is_file() else (shutil.which("ffprobe") or "ffprobe")
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                return int(round(float(value) * MICROSECONDS))
    except Exception:
        pass
    return 0
def _audio_duration_us(path: Path) -> int:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate()
                if frames > 0 and rate > 0:
                    return int(round(frames * MICROSECONDS / rate))
        except Exception:
            pass
    duration = _ffprobe_duration_us(path)
    if duration > 0:
        return duration
    try:
        from mutagen import File as MutagenFile  # type: ignore

        info = MutagenFile(str(path))
        length = getattr(getattr(info, "info", None), "length", None)
        if length:
            return int(round(float(length) * MICROSECONDS))
    except Exception:
        pass
    if suffix == ".mp3":
        try:
            duration = _mp3_duration_us(path)
            if duration > 0:
                return duration
        except Exception:
            pass
    raise DraftEngineError(f"Không đọc được thời lượng audio: {path}")
def _find_voice_audio_file(voice_dir: Path, idx: int) -> Path | None:
    stems = (str(idx), f"{idx:04d}")
    suffixes = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
    for stem in stems:
        for suffix in suffixes:
            path = voice_dir / f"{stem}{suffix}"
            if path.exists():
                return path
    return None
def _track_type(track: Dict[str, Any]) -> str:
    return str(track.get("type", "")).lower()
def _ensure_tracks_available(data: Dict[str, Any]) -> None:
    tracks = data.get("tracks")
    if isinstance(tracks, list) and tracks:
        return
    raise DraftEngineError(
        "Project không có timeline khả dụng (tracks đang rỗng). "
        "CapCut có thể chưa lưu timeline chính vào draft này hoặc đây là project/timeline rỗng. "
        "Hãy mở đúng timeline có video, subtitle và audio trong CapCut, lưu project, rồi đóng CapCut trước khi chạy."
    )
def _sorted_segments(track: Dict[str, Any]) -> List[Dict[str, Any]]:
    segments = track.get("segments") or []
    if not isinstance(segments, list):
        return []
    return sorted(
        [seg for seg in segments if isinstance(seg, dict)],
        key=lambda seg: _safe_int((seg.get("target_timerange") or {}).get("start", 0)),
    )
def _choose_primary_segment(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not segments:
        raise DraftEngineError("Project không có video segment nào")
    def score(seg: Dict[str, Any]) -> tuple[int, int]:
        src = seg.get("source_timerange") or {}
        tgt = seg.get("target_timerange") or {}
        return (_safe_int(src.get("duration", 0)), _safe_int(tgt.get("duration", 0)))
    return max(segments, key=score)
def _parse_text_from_material(material: Dict[str, Any] | None) -> str:
    if not material:
        return ""
    if isinstance(material.get("content"), str):
        try:
            content = json.loads(material["content"])
            if isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str):
                    return text.strip()
        except Exception:
            pass
    for key in ("text", "content", "recognize_text", "base_content"):
        value = material.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
def _collect_text_segments(data: Dict[str, Any], logger: Callable[[str], None]) -> List[Dict[str, Any]]:
    lookup = _build_material_lookup(data)
    candidates: List[tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for track_idx, track in enumerate(data.get("tracks", []), start=1):
        if _track_type(track) in TEXT_TRACK_TYPES:
            segs = []
            for seg in _sorted_segments(track):
                tr = seg.get("target_timerange") or {}
                start = _safe_int(tr.get("start", 0))
                duration = _safe_int(tr.get("duration", 0))
                if duration <= 0:
                    continue
                material = _segment_material(seg, lookup)
                segs.append({
                    "segment": seg,
                    "track": track,
                    "track_index": track_idx,
                    "start": start,
                    "duration": duration,
                    "end": start + duration,
                    "text": _parse_text_from_material(material),
                })
            if segs:
                candidates.append((track, segs))
    if not candidates:
        raise DraftEngineError("Không tìm thấy track phụ đề/text trong project")
    best_track, best_segs = max(candidates, key=lambda item: len(item[1]))
    logger(f"  📝 Dùng text track: {len(best_segs)} segment")
    return best_segs
def _segment_debug_name(segment: Dict[str, Any], material: Dict[str, Any] | None = None) -> str:
    bits: List[str] = []
    for src in (segment, material or {}):
        for key in ("name", "extra_info", "material_name", "display_name", "caption", "text"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                bits.append(val.strip())
    joined = " | ".join(bits)
    return joined[:120]
def _is_tts_audio(segment: Dict[str, Any], material: Dict[str, Any] | None = None) -> bool:
    hay = []
    for src in (segment, material or {}):
        for key, val in src.items():
            if isinstance(val, str):
                hay.append(val.lower())
    blob = " ".join(hay)
    return any(k in blob for k in ["text-to-speech", "tts", "voice", "speech", "sweet little girl"])
def _collect_all_audio_segments(data: Dict[str, Any], logger: Callable[[str], None]) -> List[Dict[str, Any]]:
    lookup = _build_material_lookup(data)
    out: List[Dict[str, Any]] = []
    audio_track_count = 0
    for track_idx, track in enumerate(data.get("tracks", []), start=1):
        if _track_type(track) in AUDIO_TRACK_TYPES:
            audio_track_count += 1
            track_segs = []
            for seg in _sorted_segments(track):
                tr = seg.get("target_timerange") or {}
                start = _safe_int(tr.get("start", 0))
                duration = _safe_int(tr.get("duration", 0))
                if duration <= 0:
                    continue
                material = _segment_material(seg, lookup)
                info = {
                    "segment": seg,
                    "start": start,
                    "duration": duration,
                    "end": start + duration,
                    "track_index": track_idx,
                    "is_tts": _is_tts_audio(seg, material),
                    "debug_name": _segment_debug_name(seg, material),
                }
                track_segs.append(info)
                out.append(info)
            if track_segs:
                tts_count = sum(1 for x in track_segs if x["is_tts"])
                logger(f"  🔎 Audio track #{track_idx}: {len(track_segs)} segment | TTS-like: {tts_count}")
    if not out:
        raise DraftEngineError("Không tìm thấy audio track trong project")
    logger(f"  🔊 Tìm thấy tổng cộng {len(out)} audio segment trên {audio_track_count} audio track")
    return out
def _collect_audio_segments(data: Dict[str, Any], logger: Callable[[str], None]) -> List[Dict[str, Any]]:
    all_audio = _collect_all_audio_segments(data, logger)
    # fallback cũ: trả theo thời gian toàn cục
    return sorted(all_audio, key=lambda x: (x["start"], x["track_index"]))
def _draft_relative_path(project_dir: Path, file_path: Path, placeholder: str = "") -> str:
    try:
        rel = file_path.resolve().relative_to(project_dir.resolve()).as_posix()
        if placeholder:
            return f"{placeholder}/{rel}"
        return file_path.resolve().as_posix()
    except Exception:
        return file_path.as_posix()
def _find_draft_path_placeholder(data: Dict[str, Any]) -> str:
    pattern = re.compile(r"(##_draftpath_placeholder_[^#]+_##)")
    materials = data.get("materials", {})
    if isinstance(materials, dict):
        for bucket in materials.values():
            if not isinstance(bucket, list):
                continue
            for item in bucket:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if isinstance(path, str):
                    match = pattern.search(path)
                    if match:
                        return match.group(1)
    return ""
def _new_speed_material(speed: float = 1.0) -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "type": "speed",
        "mode": 0,
        "speed": float(speed),
        "curve_speed": None,
    }
def _new_placeholder_info() -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "type": "placeholder_info",
        "meta_type": "none",
        "res_path": "",
        "res_text": "",
        "error_path": "",
        "error_text": "",
    }
def _new_beats_material() -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "type": "beats",
        "enable_ai_beats": False,
        "gear": 404,
        "gear_count": 0,
        "mode": 404,
        "user_beats": [],
        "user_delete_ai_beats": None,
        "ai_beats": {
            "melody_url": "",
            "melody_path": "",
            "beats_url": "",
            "beats_path": "",
            "melody_percents": [0.0],
            "beat_speed_infos": [],
        },
    }
def _new_channel_mapping() -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "type": "",
        "audio_channel_mapping": 0,
        "is_config_open": False,
    }
def _new_vocal_separation() -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "type": "vocal_separation",
        "choice": 0,
        "removed_sounds": [],
        "time_range": None,
        "production_path": "",
        "final_algorithm": "",
        "enter_from": "",
    }
def _new_audio_material(file_path: Path, project_dir: Path, duration_us: int, name: str, text_id: str = "", placeholder: str = "") -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "unique_id": "",
        "type": "text_to_audio",
        "name": name,
        "duration": int(duration_us),
        "path": _draft_relative_path(project_dir, file_path, placeholder),
        "category_name": "Dich_CapCut Voice",
        "wave_points": [],
        "music_id": "",
        "app_id": 0,
        "text_id": text_id,
        "tone_type": "OmniVoice",
        "source_platform": 0,
        "video_id": "",
        "effect_id": "",
        "resource_id": "",
        "third_resource_id": "",
        "category_id": "",
        "intensifies_path": "",
        "formula_id": "",
        "check_flag": 1,
        "team_id": "",
        "local_material_id": "",
        "tone_speaker": "OmniVoice",
        "mock_tone_speaker": "OmniVoice",
        "tone_effect_id": "",
        "tone_effect_name": "OmniVoice",
        "tone_platform": "local",
        "copyright_limit_type": "none",
        "source_from": "Dich_CapCut",
        "tts_generate_scene": "audio_panel",
    }
def _new_audio_segment(material_id: str, start_us: int, duration_us: int, extra_refs: List[str]) -> Dict[str, Any]:
    return {
        "id": new_uuid(),
        "source_timerange": {"start": 0, "duration": int(duration_us)},
        "target_timerange": {"start": int(start_us), "duration": int(duration_us)},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": None,
        "uniform_scale": None,
        "material_id": material_id,
        "extra_material_refs": extra_refs,
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": False,
        "enable_adjust": False,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": None,
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False,
            "target_follow": "",
            "size_layout": 0,
            "horizontal_pos_layout": 0,
            "vertical_pos_layout": 0,
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
    }
def import_voice_files_by_subtitles(
    project_dir: Path,
    voice_dir: Path,
    srt_path: Path | None = None,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    normalize_project_metadata(project_dir, logger)
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"Không tìm thấy file: {draft_path}")
    log = logger or (lambda _msg: None)
    voice_dir = Path(voice_dir)
    if not voice_dir.exists():
        raise DraftEngineError(f"Không tìm thấy thư mục voice: {voice_dir}")
    if backup:
        backup_project_drafts(draft_path, mirror_paths)
        log("  Đã tạo backup draft_content.json.bak")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    if srt_path:
        subtitle_segments = _collect_srt_segments(Path(srt_path))
        subtitle_segments = _apply_srt_to_existing_text_track(data, subtitle_segments, log)
        log(f"  Dùng mốc từ SRT: {srt_path} ({len(subtitle_segments)} dòng)")
    else:
        subtitle_segments = _collect_text_segments(data, log)
    path_placeholder = _find_draft_path_placeholder(data)
    materials = data.setdefault("materials", {})
    if not isinstance(materials, dict):
        data["materials"] = {}
        materials = data["materials"]
    audios = materials.setdefault("audios", [])
    speeds = materials.setdefault("speeds", [])
    placeholders = materials.setdefault("placeholder_infos", [])
    beats = materials.setdefault("beats", [])
    mappings = materials.setdefault("sound_channel_mappings", [])
    vocals = materials.setdefault("vocal_separations", [])
    for bucket_name, bucket in (
        ("audios", audios),
        ("speeds", speeds),
        ("placeholder_infos", placeholders),
        ("beats", beats),
        ("sound_channel_mappings", mappings),
        ("vocal_separations", vocals),
    ):
        if not isinstance(bucket, list):
            materials[bucket_name] = []
    audios = materials["audios"]
    speeds = materials["speeds"]
    placeholders = materials["placeholder_infos"]
    beats = materials["beats"]
    mappings = materials["sound_channel_mappings"]
    vocals = materials["vocal_separations"]

    text_reading_dir = project_dir / "textReading"
    text_reading_dir.mkdir(parents=True, exist_ok=True)
    audio_track = {
        "id": new_uuid(),
        "type": "audio",
        "flag": 0,
        "attribute": 0,
        "name": "Dich_CapCut Voice",
        "is_default_name": False,
        "segments": [],
    }
    imported = 0
    skipped = 0
    max_end = _safe_int(data.get("duration", 0))
    for idx, sub in enumerate(subtitle_segments, start=1):
        src = _find_voice_audio_file(voice_dir, idx)
        if not src:
            skipped += 1
            log(f"  Bỏ qua #{idx}: thiếu {idx}.wav/{idx:04d}.mp3")
            continue
        duration_us = _audio_duration_us(src)
        if duration_us <= 0:
            skipped += 1
            log(f"  Bỏ qua #{idx}: audio rỗng")
            continue
        dest = text_reading_dir / f"dich_capcut_voice_{idx:04d}{src.suffix.lower()}"
        shutil.copy2(src, dest)
        speed_mat = _new_speed_material()
        placeholder_mat = _new_placeholder_info()
        beats_mat = _new_beats_material()
        mapping_mat = _new_channel_mapping()
        vocal_mat = _new_vocal_separation()
        speeds.append(speed_mat)
        placeholders.append(placeholder_mat)
        beats.append(beats_mat)
        mappings.append(mapping_mat)
        vocals.append(vocal_mat)
        short_name = (sub.get("text") or f"Voice {idx}").replace("\n", " ").strip()
        if len(short_name) > 28:
            short_name = short_name[:25] + "..."
        text_id = str((sub.get("segment") or {}).get("material_id", ""))
        audio_mat = _new_audio_material(dest, project_dir, duration_us, short_name, text_id=text_id, placeholder=path_placeholder)
        audios.append(audio_mat)
        extra_refs = [
            speed_mat["id"],
            placeholder_mat["id"],
            beats_mat["id"],
            mapping_mat["id"],
            vocal_mat["id"],
        ]
        start_us = _safe_int(sub.get("start", 0))
        audio_track["segments"].append(_new_audio_segment(audio_mat["id"], start_us, duration_us, extra_refs))
        max_end = max(max_end, start_us + duration_us)
        imported += 1
        log(f"  Thêm voice #{idx}: {src.name} -> {start_us / MICROSECONDS:.2f}s, dur {duration_us / MICROSECONDS:.2f}s")
    if imported <= 0:
        raise DraftEngineError("Không import được file voice nào. Kiểm tra thư mục output phải có 1.wav, 2.wav...")
    tracks = data.setdefault("tracks", [])
    if not isinstance(tracks, list):
        raise DraftEngineError("Cấu trúc tracks không hợp lệ")
    tracks[:] = [
        track
        for track in tracks
        if not (
            isinstance(track, dict)
            and _track_type(track) in AUDIO_TRACK_TYPES
            and str(track.get("name", "")).lower() == "dich_capcut voice"
        )
    ]
    tracks.append(audio_track)
    data["duration"] = max_end
    save_project_drafts(draft_path, mirror_paths, data)
    log(f"  Đã import {imported} voice vào project")
    return {
        "draft_path": str(draft_path),
        "subtitle_segments": len(subtitle_segments),
        "voice_files_imported": imported,
        "voice_files_skipped": skipped,
        "voice_dir": str(voice_dir),
        "timeline_duration": max_end,
    }
def _collect_image_segments(
    data: Dict[str, Any],
    logger: Callable[[str], None],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    lookup = _build_material_lookup(data)
    candidates: List[tuple[Dict[str, Any], List[Dict[str, Any]], int]] = []
    for track_idx, track in enumerate(data.get("tracks", []), start=1):
        if _track_type(track) not in SUPPORTED_VIDEO_TRACK_TYPES:
            continue
        sorted_track_segments = _sorted_segments(track)
        image_segs: List[Dict[str, Any]] = []
        for seg in sorted_track_segments:
            tr = seg.get("target_timerange") or {}
            start = _safe_int(tr.get("start", 0))
            duration = _safe_int(tr.get("duration", 0))
            if duration <= 0:
                continue
            if not is_image_segment(seg, lookup):
                continue
            material = _segment_material(seg, lookup)
            image_segs.append({
                "segment": seg,
                "track": track,
                "track_index": track_idx,
                "start": start,
                "duration": duration,
                "end": start + duration,
                "debug_name": _segment_debug_name(seg, material),
                "path": _extract_path_from_material(material or {}),
            })
        if image_segs:
            non_image_count = max(0, len(sorted_track_segments) - len(image_segs))
            logger(
                f"  🖼️ Video track #{track_idx}: {len(image_segs)} image segment | non-image: {non_image_count}"
            )
            candidates.append((track, image_segs, non_image_count))
    if not candidates:
        raise DraftEngineError("Không tìm thấy image/photo segment nào trong video track")
    best_track, best_segs, mixed_count = max(candidates, key=lambda item: (len(item[1]), -item[2]))
    logger(f"  ✅ Dùng image track: {len(best_segs)} ảnh | non-image đi kèm: {mixed_count}")
    return best_track, best_segs
def _overlap_us(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))
def _parse_srt_timestamp_us(value: str) -> int:
    match = re.match(r"\s*(\d+):(\d+):(\d+),(\d+)\s*", value)
    if not match:
        raise DraftEngineError(f"Timeline SRT không hợp lệ: {value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return (((hours * 60 + minutes) * 60 + seconds) * MICROSECONDS) + millis * 1000
def _collect_srt_segments(srt_path: Path) -> List[Dict[str, Any]]:
    text = srt_path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    out: List[Dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timeline = next((line for line in lines if "-->" in line), "")
        if not timeline:
            continue
        left, right = [part.strip() for part in timeline.split("-->", 1)]
        start = _parse_srt_timestamp_us(left)
        end = _parse_srt_timestamp_us(right)
        if end <= start:
            continue
        content_lines = []
        for line in lines:
            if line.isdigit() or "-->" in line:
                continue
            content_lines.append(re.sub(r"<[^>]+>", "", line).strip())
        out.append({
            "segment": {},
            "track": {},
            "track_index": 0,
            "start": start,
            "duration": end - start,
            "end": end,
            "text": " ".join(part for part in content_lines if part).strip(),
        })
    if not out:
        raise DraftEngineError(f"Không đọc được mốc SRT: {srt_path}")
    return out
def _set_text_material_text(material: Dict[str, Any] | None, text: str) -> None:
    if not material:
        return
    text = str(text or "")
    material["recognize_text"] = text
    material["base_content"] = text
    if isinstance(material.get("content"), str):
        try:
            content = json.loads(material["content"])
            if isinstance(content, dict):
                content["text"] = text
                styles = content.get("styles")
                if isinstance(styles, list):
                    for style in styles:
                        if isinstance(style, dict):
                            style["range"] = [0, len(text)]
                material["content"] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass
    for key in ("words", "current_words"):
        if isinstance(material.get(key), dict):
            material[key]["start_time"] = []
            material[key]["end_time"] = []
            material[key]["text"] = []
def _apply_srt_to_existing_text_track(
    data: Dict[str, Any],
    srt_segments: List[Dict[str, Any]],
    logger: Callable[[str], None] | None = None,
) -> List[Dict[str, Any]]:
    log = logger or (lambda _msg: None)
    if not srt_segments:
        return srt_segments
    lookup = _build_material_lookup(data)
    candidates: List[tuple[int, Dict[str, Any], List[Dict[str, Any]]]] = []
    for track_idx, track in enumerate(data.get("tracks", []), start=1):
        if _track_type(track) in TEXT_TRACK_TYPES:
            segs = _sorted_segments(track)
            if segs:
                candidates.append((track_idx, track, segs))
    if not candidates:
        log("  Cảnh báo: project chưa có subtitle/text track để cập nhật theo SRT.")
        return srt_segments
    track_idx, track, text_segs = max(candidates, key=lambda item: len(item[2]))
    if text_segs and len(text_segs) < len(srt_segments):
        materials = data.setdefault("materials", {})
        text_materials = materials.setdefault("texts", [])
        if not isinstance(text_materials, list):
            materials["texts"] = []
            text_materials = materials["texts"]
        base_seg = text_segs[-1]
        base_material = _segment_material(base_seg, lookup)
        for _extra_idx in range(len(srt_segments) - len(text_segs)):
            new_seg = copy.deepcopy(base_seg)
            new_seg["id"] = new_uuid()
            if base_material:
                new_mat = copy.deepcopy(base_material)
                new_mat["id"] = new_uuid()
                new_seg["material_id"] = new_mat["id"]
                text_materials.append(new_mat)
                lookup[new_mat["id"]] = new_mat
            track.setdefault("segments", []).append(new_seg)
            text_segs.append(new_seg)
        log(f"  Đã tạo thêm subtitle segment để khớp SRT: {len(text_segs)}/{len(srt_segments)}")
    if len(text_segs) > len(srt_segments):
        keep_ids = {id(seg) for seg in text_segs[:len(srt_segments)]}
        track["segments"] = [seg for seg in (track.get("segments") or []) if id(seg) in keep_ids]
        text_segs = text_segs[:len(srt_segments)]
        log(f"  Đã bỏ subtitle dư để khớp SRT: {len(text_segs)} dòng")
    pair_count = min(len(text_segs), len(srt_segments))
    if len(text_segs) != len(srt_segments):
        log(f"  Cảnh báo: subtitle track có {len(text_segs)} đoạn, SRT có {len(srt_segments)} dòng. Chỉ cập nhật {pair_count} dòng đầu.")
    mapped: List[Dict[str, Any]] = []
    for idx, srt_item in enumerate(srt_segments):
        item = dict(srt_item)
        if idx < pair_count:
            seg = text_segs[idx]
            start = _safe_int(srt_item.get("start", 0))
            duration = _safe_int(srt_item.get("duration", 0))
            seg["target_timerange"] = {"start": start, "duration": duration}
            material = _segment_material(seg, lookup)
            _set_text_material_text(material, str(srt_item.get("text", "")))
            item.update({"segment": seg, "track": track, "track_index": track_idx})
        mapped.append(item)
    log(f"  Đã cập nhật subtitle track theo SRT: {pair_count}/{len(srt_segments)} dòng")
    return mapped
def _pick_best_audio_for_subtitle(sub: Dict[str, Any], audio_pool: List[Dict[str, Any]], used_ids: set[str], logger: Callable[[str], None] | None = None) -> Dict[str, Any] | None:
    sub_start, sub_end, sub_dur = sub["start"], sub["end"], sub["duration"]
    best = None
    best_score = -10**18
    for item in audio_pool:
        seg_id = str(item["segment"].get("id", ""))
        if seg_id in used_ids:
            continue
        ov = _overlap_us(sub_start, sub_end, item["start"], item["end"])
        gap = min(abs(item["start"] - sub_start), abs(item["end"] - sub_end), abs(item["start"] - sub_end), abs(item["end"] - sub_start))
        dur_diff = abs(item["duration"] - sub_dur)
        score = 0
        score += ov * 20
        score -= gap * 2
        score -= dur_diff
        if item.get("is_tts"):
            score += 5 * MICROSECONDS
        # nhẹ nhàng ưu tiên audio ngắn/gần subtitle hơn là nhạc nền dài
        if item["duration"] > sub_dur * 6:
            score -= item["duration"]
        if score > best_score:
            best = item
            best_score = score
    if best and logger:
        logger(
            f"    ↳ Audio match: track#{best['track_index']} {best['start']/MICROSECONDS:.2f}s-{best['end']/MICROSECONDS:.2f}s "
            f"dur {best['duration']/MICROSECONDS:.2f}s{' | TTS' if best.get('is_tts') else ''}"
        )
    return best
def _video_track_segments(track: Dict[str, Any]) -> List[Dict[str, Any]]:
    segs = track.get("segments", [])
    return segs if isinstance(segs, list) else []
def _pick_working_video_track(data: Dict[str, Any], logger: Callable[[str], None] | None = None) -> Dict[str, Any]:
    candidates: List[tuple[Dict[str, Any], int, int]] = []
    for idx, track in enumerate(data.get("tracks", []), start=1):
        if _track_type(track) not in SUPPORTED_VIDEO_TRACK_TYPES:
            continue
        segs = _sorted_segments(track)
        if not segs:
            continue
        long_count = sum(1 for s in segs if _safe_int((s.get("target_timerange") or {}).get("duration", 0)) >= 2 * MICROSECONDS)
        candidates.append((track, len(segs), long_count))
        if logger:
            logger(f"  🎞️ Video track #{idx}: {len(segs)} segment | >=2s: {long_count}")
    if not candidates:
        raise DraftEngineError("Không tìm thấy video track hợp lệ")
    # Ưu tiên track đã chẻ ở bước 1: nhiều segment nhất. Nếu hòa thì ưu tiên track có nhiều segment dài hơn.
    best_track, seg_count, long_count = max(candidates, key=lambda x: (x[1], x[2]))
    if logger:
        logger(f"  ✅ Dùng video track đang xử lý: {seg_count} segment | >=2s: {long_count}")
    return best_track
def cut_video_by_subtitles_only(
    project_dir: Path,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
    srt_path: Path | None = None,
) -> Dict[str, Any]:
    normalize_project_metadata(project_dir, logger)
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"Không tìm thấy file: {draft_path}")
    log = logger or (lambda _msg: None)
    if backup:
        backup_project_drafts(draft_path, mirror_paths)
        log("  💾 Đã tạo file backup draft_content.json.bak")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    video_track = _pick_working_video_track(data, log)
    original_video_segments = _sorted_segments(video_track)
    if not original_video_segments:
        raise DraftEngineError("Project không có video segment nào")
    if srt_path:
        subtitle_segments = _collect_srt_segments(Path(srt_path))
        subtitle_segments = _apply_srt_to_existing_text_track(data, subtitle_segments, log)
        log(f"  Dùng mốc từ SRT: {srt_path} ({len(subtitle_segments)} dòng)")
    else:
        subtitle_segments = _collect_text_segments(data, log)
    if not subtitle_segments:
        raise DraftEngineError("Không tìm thấy subtitle segment nào để cắt video")
    base_segment = _choose_primary_segment(original_video_segments)
    base_source = base_segment.get("source_timerange") or {}
    base_target = base_segment.get("target_timerange") or {}
    base_source_start = _safe_int(base_source.get("start", 0))
    base_source_duration = _safe_int(base_source.get("duration", 0))
    base_target_start = _safe_int(base_target.get("start", 0))
    base_target_duration = _safe_int(base_target.get("duration", 0))
    if base_source_duration <= 0:
        base_source_duration = base_target_duration
    if base_target_duration <= 0:
        base_target_duration = base_source_duration
    if base_source_duration <= 0 or base_target_duration <= 0:
        raise DraftEngineError("Không đọc được thời lượng clip video gốc")
    base_target_end = base_target_start + base_target_duration
    project_fps = get_project_fps(data)
    frame_us = _frame_us(project_fps)
    log(f"  ⏱️ Project FPS: {project_fps} -> 1 frame = {frame_us}us")
    boundaries = {base_target_start, base_target_end}
    kept_subtitles = 0
    for i, sub in enumerate(subtitle_segments, start=1):
        sub_start = _safe_int(sub["start"])
        sub_end = _safe_int(sub["end"])
        if sub_end <= sub_start:
            log(f"  ⚠️ Subtitle #{i} duration = 0, bỏ qua")
            continue
        if sub_start < base_target_start or sub_end > base_target_end:
            raise DraftEngineError(
                f"Subtitle #{i} vượt ngoài phạm vi video gốc: {sub_start} -> {sub_end} không nằm trong {base_target_start} -> {base_target_end}"
            )
        boundaries.add(sub_start)
        boundaries.add(sub_end)
        kept_subtitles += 1
    sorted_bounds = sorted(boundaries)
    if len(sorted_bounds) < 2:
        raise DraftEngineError("Không tạo được mốc cắt hợp lệ từ subtitle")
    frame_marks = _normalize_frame_counts(sorted_bounds, base_target_duration, frame_us)
    new_segments: List[Dict[str, Any]] = []
    for idx in range(len(frame_marks) - 1):
        start_frame = frame_marks[idx]
        end_frame = frame_marks[idx + 1]
        frame_count = end_frame - start_frame
        if frame_count <= 0:
            continue
        target_start = int(base_target_start + start_frame * frame_us)
        target_duration = int(frame_count * frame_us)
        source_start = int(_snap_time_us(base_source_start, frame_us, "floor") + start_frame * frame_us)
        source_duration = int(frame_count * frame_us)
        if source_start < _snap_time_us(base_source_start, frame_us, "floor") or source_start + source_duration > _snap_time_us(base_source_start, frame_us, "floor") + max(source_duration, int(round(base_source_duration / frame_us)) * frame_us):
            raise DraftEngineError(
                f"Mốc cắt #{idx + 1} vượt ngoài source video: {source_start} + {source_duration}"
            )
        seg = copy.deepcopy(base_segment)
        seg["id"] = new_uuid()
        seg["target_timerange"] = {
            "start": target_start,
            "duration": target_duration,
        }
        seg["source_timerange"] = {
            "start": source_start,
            "duration": source_duration,
        }
        seg["render_timerange"] = {"start": 0, "duration": 0}
        _ensure_speed_material(data, seg, 1.0)
        if "common_keyframes" in seg:
            seg["common_keyframes"] = []
        new_segments.append(seg)
        log(f"  • Cut #{idx + 1}: {target_start / MICROSECONDS:.2f}s -> {(target_start + target_duration) / MICROSECONDS:.2f}s")
    if not new_segments:
        raise DraftEngineError("Không tạo được video segment nào sau khi chẻ mốc")
    video_track["segments"] = new_segments
    data["duration"] = max(_safe_int(data.get("duration", 0)), base_target_end)
    debug_written = write_debug_snapshot(project_dir, "step1_written", data)
    if debug_written:
        log(f"  🧪 Snapshot written: {debug_written}")
    save_project_drafts(draft_path, mirror_paths, data)
    verified_segments = -1
    stable_hits = 0
    last_reloaded: Dict[str, Any] | None = None
    for _ in range(12):
        reloaded = load_draft_json(draft_path, require_tracks=True, retries=1, retry_delay=0.2)
        last_reloaded = reloaded
        verify_track = _pick_working_video_track(reloaded, None)
        verified_segments = len(_sorted_segments(verify_track))
        if verified_segments == len(new_segments):
            stable_hits += 1
        else:
            stable_hits = 0
        if stable_hits >= 4:
            break
        time.sleep(0.6)
    if last_reloaded is not None:
        debug_reloaded = write_debug_snapshot(project_dir, "step1_reloaded", last_reloaded)
        if debug_reloaded:
            log(f"  🧪 Snapshot reloaded: {debug_reloaded}")
    if verified_segments != len(new_segments) or stable_hits < 4:
        raise DraftEngineError(
            f"Đã chẻ {len(new_segments)} video segment nhưng file không giữ ổn định kết quả "
            f"(đọc lại gần nhất: {verified_segments}). Project có thể đang bị CapCut hoặc tiến trình khác ghi đè."
        )
    log(f"  ✅ Xác minh ổn định sau khi ghi: {verified_segments} video segment")
    return {
        "draft_path": str(draft_path),
        "subtitle_segments": len(subtitle_segments),
        "subtitle_boundaries_used": kept_subtitles,
        "video_segments_written": len(new_segments),
        "timeline_duration": base_target_end,
    }
def analyze_audio_sync_project(project_dir: Path) -> Dict[str, Any]:
    normalize_project_metadata(project_dir)
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"Không tìm thấy file: {draft_path}")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    video_track = _pick_working_video_track(data, None)
    video_segments = _sorted_segments(video_track)
    text_segments = _collect_text_segments(data, lambda _msg: None)
    audio_segments = _collect_audio_segments(data, lambda _msg: None)
    base_segment = _choose_primary_segment(video_segments)
    base_src = base_segment.get("source_timerange") or {}
    base_duration = _safe_int(base_src.get("duration", 0)) or _safe_int((base_segment.get("target_timerange") or {}).get("duration", 0))
    return {
        "video_segments": len(video_segments),
        "subtitle_segments": len(text_segments),
        "audio_segments": len(audio_segments),
        "usable_pairs": min(len(text_segments), len(audio_segments)),
        "base_video_duration": base_duration,
    }
def sync_audio_video_by_subtitles(
    project_dir: Path,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
    use_audio_timing: bool = True,
    srt_path: Path | None = None,
) -> Dict[str, Any]:
    normalize_project_metadata(project_dir, logger)
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"Không tìm thấy file: {draft_path}")
    log = logger or (lambda _msg: None)
    if backup:
        backup_project_drafts(draft_path, mirror_paths)
        log("  💾 Đã tạo file backup draft_content.json.bak")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    video_track = _pick_working_video_track(data, log)
    video_segments = _sorted_segments(video_track)
    if not video_segments:
        raise DraftEngineError("Project không có video segment nào")
    if srt_path:
        subtitle_segments = _collect_srt_segments(Path(srt_path))
        subtitle_segments = _apply_srt_to_existing_text_track(data, subtitle_segments, log)
        log(f"  Dùng mốc từ SRT: {srt_path} ({len(subtitle_segments)} dòng)")
    else:
        subtitle_segments = _collect_text_segments(data, log)
    audio_pool = _collect_all_audio_segments(data, log)
    subtitle_by_range = {(sub['start'], sub['end']): sub for sub in subtitle_segments if sub['duration'] > 0}
    project_fps = get_project_fps(data)
    frame_us = _frame_us(project_fps)
    log(f"  ⏱️ Project FPS: {project_fps} -> 1 frame = {frame_us}us")
    source_ranges = _contiguous_frame_source_ranges(video_segments, frame_us)
    used_audio_ids: set[str] = set()
    used_sub_ids: set[str] = set()
    new_segments: List[Dict[str, Any]] = []
    cursor = 0
    retimed = 0
    unchanged = 0
    subtitle_updates = 0
    audio_updates = 0
    warnings: List[str] = []
    log(f"  🎬 Video segments hiện có: {len(video_segments)}")
    log("  🧭 Bắt đầu match theo timeline: subtitle ↔ audio ↔ video clip đã chẻ")
    for idx, seg in enumerate(video_segments, start=1):
        seg_copy = copy.deepcopy(seg)
        tr = seg.get('target_timerange') or {}
        sr = seg.get('source_timerange') or {}
        old_start = _safe_int(tr.get('start', 0))
        old_duration = _safe_int(tr.get('duration', 0))
        old_end = old_start + old_duration
        src_start = _safe_int(sr.get('start', 0))
        src_duration = _safe_int(sr.get('duration', old_duration)) or old_duration
        if idx - 1 < len(source_ranges):
            src_start, src_duration = source_ranges[idx - 1]
        seg_copy['target_timerange'] = {'start': int(cursor), 'duration': int(old_duration)}
        if 'speed' not in seg_copy:
            seg_copy['speed'] = 1.0
        sub = subtitle_by_range.get((old_start, old_end))
        if sub is None:
            for cand in subtitle_segments:
                if abs(cand["start"] - old_start) <= 50_000 and abs(cand["end"] - old_end) <= 50_000:
                    sub = cand
                    break
        if sub is None:
            old_duration = max(frame_us, _snap_time_us(old_duration, frame_us, 'nearest'))
            seg_copy['target_timerange']['start'] = int(_snap_time_us(cursor, frame_us, 'nearest'))
            seg_copy['target_timerange']['duration'] = int(old_duration)
            seg_copy['source_timerange'] = {'start': int(src_start), 'duration': int(src_duration)}
            _ensure_speed_material(data, seg_copy, 1.0)
            new_segments.append(seg_copy)
            cursor = _snap_time_us(cursor, frame_us, 'nearest') + old_duration
            unchanged += 1
            continue
        sub_seg = sub.get('segment') or {}
        sub_id = str(sub_seg.get('id', ''))
        audio = _pick_best_audio_for_subtitle(sub, audio_pool, used_audio_ids, logger=log)
        if audio is None:
            warnings.append(f"Không tìm thấy audio phù hợp cho subtitle tại {sub['start']/MICROSECONDS:.2f}s")
            old_duration = max(frame_us, _snap_time_us(old_duration, frame_us, 'nearest'))
            seg_copy['target_timerange']['start'] = int(_snap_time_us(cursor, frame_us, 'nearest'))
            seg_copy['target_timerange']['duration'] = int(old_duration)
            seg_copy['source_timerange'] = {'start': int(src_start), 'duration': int(src_duration)}
            _ensure_speed_material(data, seg_copy, 1.0)
            # vẫn dời subtitle theo video nếu có
            if sub_id and sub_id not in used_sub_ids:
                sub_seg['target_timerange'] = {'start': int(cursor), 'duration': int(old_duration)}
                subtitle_updates += 1
                used_sub_ids.add(sub_id)
            new_segments.append(seg_copy)
            cursor = _snap_time_us(cursor, frame_us, 'nearest') + old_duration
            unchanged += 1
            continue
        audio_seg = audio['segment']
        audio_id = str(audio_seg.get('id', ''))
        used_audio_ids.add(audio_id)
        old_duration = max(frame_us, _snap_time_us(old_duration, frame_us, 'nearest'))
        new_duration = int(audio['duration']) if use_audio_timing else old_duration
        if new_duration <= 0:
            new_duration = old_duration
        new_duration = max(frame_us, _snap_time_us(new_duration, frame_us, 'nearest'))
        speed = round(src_duration / new_duration, 6) if new_duration > 0 else 1.0
        if speed <= 0:
            speed = 1.0
        if speed < 0.1 or speed > 10:
            warnings.append(f"segment #{idx} speed = {speed:.3f} hơi cực đoan")
        snapped_cursor = int(_snap_time_us(cursor, frame_us, 'nearest'))
        seg_copy['target_timerange'] = {'start': snapped_cursor, 'duration': int(new_duration)}
        seg_copy['source_timerange'] = {'start': int(src_start), 'duration': int(src_duration)}
        seg_copy['render_timerange'] = {'start': 0, 'duration': 0}
        _ensure_speed_material(data, seg_copy, speed)
        new_segments.append(seg_copy)
        # dời subtitle khớp timeline mới
        if sub_id and sub_id not in used_sub_ids:
            sub_seg['target_timerange'] = {'start': snapped_cursor, 'duration': int(new_duration)}
            subtitle_updates += 1
            used_sub_ids.add(sub_id)
        # dời audio khớp timeline mới và giữ nguyên duration audio
        audio_seg['target_timerange'] = {'start': snapped_cursor, 'duration': int(new_duration)}
        audio_updates += 1
        short_text = (sub.get('text') or '').replace('\n', ' ').strip()
        if len(short_text) > 40:
            short_text = short_text[:37] + '...'
        log(
            f"  • Clip #{idx}: {old_start/MICROSECONDS:.2f}s-{old_end/MICROSECONDS:.2f}s | "
            f"audio {audio['start']/MICROSECONDS:.2f}s-{audio['end']/MICROSECONDS:.2f}s | "
            f"video {old_duration/MICROSECONDS:.2f}s -> {new_duration/MICROSECONDS:.2f}s | speed {speed:.3f}x"
            + (f" | {short_text}" if short_text else '')
        )
        cursor = snapped_cursor + new_duration
        retimed += 1
    if not new_segments:
        raise DraftEngineError("Không tạo được video segment mới nào")
    video_track['segments'] = new_segments
    data['duration'] = max(_safe_int(data.get('duration', 0)), cursor)
    save_project_drafts(draft_path, mirror_paths, data)
    return {
        'draft_path': str(draft_path),
        'subtitle_segments': len(subtitle_segments),
        'audio_segments': len(audio_pool),
        'pairs_used': retimed,
        'video_segments_written': len(new_segments),
        'timeline_duration': cursor,
        'warnings': warnings,
        'retimed_segments': retimed,
        'segments_retimed': retimed,
        'unchanged_segments': unchanged,
        'subtitle_updates': subtitle_updates,
        'audio_updates': audio_updates,
        'frame_us': frame_us,
    }
def analyze_image_audio_project(project_dir: Path) -> Dict[str, Any]:
    normalize_project_metadata(project_dir)
    draft_path, _mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"KhÃ´ng tÃ¬m tháº¥y file: {draft_path}")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    image_track, image_segments = _collect_image_segments(data, lambda _msg: None)
    audio_segments = _collect_audio_segments(data, lambda _msg: None)
    track_segments = _sorted_segments(image_track)
    return {
        "image_segments": len(image_segments),
        "audio_segments": len(audio_segments),
        "usable_pairs": min(len(image_segments), len(audio_segments)),
        "track_segments": len(track_segments),
    }
def sync_image_segments_to_audio(
    project_dir: Path,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
    move_audio: bool = True,
) -> Dict[str, Any]:
    normalize_project_metadata(project_dir, logger)
    draft_path, mirror_paths = resolve_project_draft_paths(project_dir)
    if not draft_path.exists():
        raise DraftEngineError(f"KhÃ´ng tÃ¬m tháº¥y file: {draft_path}")
    log = logger or (lambda _msg: None)
    if backup:
        backup_project_drafts(draft_path, mirror_paths)
        log("  ðŸ’¾ ÄÃ£ táº¡o file backup draft_content.json.bak")
    data = load_draft_json(draft_path, require_tracks=True)
    _ensure_tracks_available(data)
    image_track, image_segments = _collect_image_segments(data, log)
    audio_segments = _collect_audio_segments(data, log)
    if not image_segments:
        raise DraftEngineError("KhÃ´ng tÃ¬m tháº¥y áº£nh nÃ o Ä‘á»ƒ Ä‘á»“ng bá»™")
    if not audio_segments:
        raise DraftEngineError("KhÃ´ng tÃ¬m tháº¥y audio nÃ o Ä‘á»ƒ Ä‘á»“ng bá»™")

    project_fps = get_project_fps(data)
    frame_us = _frame_us(project_fps)
    log(f"  â±ï¸ Project FPS: {project_fps} -> 1 frame = {frame_us}us")

    pair_count = min(len(image_segments), len(audio_segments))
    if pair_count <= 0:
        raise DraftEngineError("KhÃ´ng cÃ³ cáº·p áº£nh/audio nÃ o khá»›p Ä‘á»ƒ xá»­ lÃ½")

    warnings: List[str] = []
    if len(image_segments) != len(audio_segments):
        warnings.append(
            f"Sá»‘ áº£nh ({len(image_segments)}) khÃ¡c sá»‘ audio ({len(audio_segments)}). Chá»‰ xá»­ lÃ½ {pair_count} cáº·p Ä‘áº§u tiÃªn."
        )

    cursor = _snap_time_us(min(image_segments[0]["start"], audio_segments[0]["start"]), frame_us, "nearest")
    image_updates = 0
    audio_updates = 0
    for idx in range(pair_count):
        image = image_segments[idx]
        audio = audio_segments[idx]
        image_seg = image["segment"]
        audio_seg = audio["segment"]
        old_image_tr = image_seg.get("target_timerange") or {}
        old_start = _safe_int(old_image_tr.get("start", 0))
        old_duration = _safe_int(old_image_tr.get("duration", 0))
        new_start = int(_snap_time_us(cursor, frame_us, "nearest"))
        new_duration = max(frame_us, _snap_time_us(int(audio["duration"]), frame_us, "nearest"))

        image_seg["target_timerange"] = {"start": new_start, "duration": int(new_duration)}
        image_updates += 1
        if move_audio:
            audio_seg["target_timerange"] = {"start": new_start, "duration": int(new_duration)}
            audio_updates += 1

        label = image.get("debug_name") or Path(image.get("path") or "").name or f"image #{idx + 1}"
        if len(label) > 36:
            label = label[:33] + "..."
        log(
            f"  â€¢ Pair #{idx + 1}: image {old_start/MICROSECONDS:.2f}s -> {new_start/MICROSECONDS:.2f}s | "
            f"{old_duration/MICROSECONDS:.2f}s -> {new_duration/MICROSECONDS:.2f}s | "
            f"audio track#{audio['track_index']} {audio['duration']/MICROSECONDS:.2f}s"
            + (f" | {label}" if label else "")
        )
        cursor = new_start + new_duration

    data["duration"] = max(_safe_int(data.get("duration", 0)), cursor)
    save_project_drafts(draft_path, mirror_paths, data)
    return {
        "draft_path": str(draft_path),
        "image_segments": len(image_segments),
        "audio_segments": len(audio_segments),
        "pairs_used": pair_count,
        "image_updates": image_updates,
        "audio_updates": audio_updates,
        "timeline_duration": cursor,
        "warnings": warnings,
        "frame_us": frame_us,
        "move_audio": move_audio,
    }
# Compatibility wrapper expected by main.py
def retime_video_subtitle_segments_to_audio(
    project_dir: Path,
    backup: bool = True,
    logger: Callable[[str], None] | None = None,
    use_audio_timing: bool = True,
    srt_path: Path | None = None,
) -> Dict[str, Any]:
    return sync_audio_video_by_subtitles(
        project_dir=project_dir,
        backup=backup,
        logger=logger,
        use_audio_timing=use_audio_timing,
        srt_path=srt_path,
    )
