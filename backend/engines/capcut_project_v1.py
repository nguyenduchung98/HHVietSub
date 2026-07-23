from __future__ import annotations

import json
import csv
import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Callable


LEGACY_ROOT = Path(os.environ.get(
    "HHVIETSUB_CAPCUT_BRIDGE_ROOT",
    r"D:\Dịch-Đồng Bộ\Dich_CapCut_v2",
)).expanduser().resolve()
if not LEGACY_ROOT.is_dir():
    raise RuntimeError(
        "Không tìm thấy CapCut bridge. Hãy đặt biến HHVIETSUB_CAPCUT_BRIDGE_ROOT "
        "hoặc cấu hình thư mục tích hợp CapCut."
    )
sys.path.insert(0, str(LEGACY_ROOT))
from core.draft_engine import (  # noqa: E402
    _apply_srt_to_existing_text_track,
    _collect_srt_segments,
    _ffprobe_duration_us,
    cut_video_by_subtitles_only,
    import_voice_files_by_subtitles,
    load_draft_json,
    normalize_project_metadata,
    resolve_project_draft_paths,
    retime_video_subtitle_segments_to_audio,
    save_project_drafts,
)


def project_root() -> Path:
    config = json.loads((LEGACY_ROOT / "config.json").read_text(encoding="utf-8"))
    root = Path(str(config.get("capcut_path", "")))
    if not root.is_dir():
        raise RuntimeError("Không tìm thấy thư mục dự án CapCut")
    return root


def _plain(value: str) -> str:
    cleaned = value.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").lower()


def _draft_score(folder: Path) -> tuple[int, float] | None:
    draft = folder / "draft_content.json"
    if not draft.is_file():
        return None
    try:
        data = json.loads(draft.read_text(encoding="utf-8"))
        tracks = data.get("tracks", [])
        videos = [t for t in tracks if isinstance(t, dict) and t.get("type") == "video" and t.get("segments")]
        texts = [t for t in tracks if isinstance(t, dict) and t.get("type") in {"text", "subtitle", "caption", "captions"} and t.get("segments")]
        if not videos or not texts:
            return None
        template_bonus = 100 if any(word in _plain(folder.name) for word in ("mau", "template")) else 0
        simple_bonus = 40 if len(videos[0].get("segments", [])) == 1 else 0
        clean_text_bonus = 80 if len(texts[0].get("segments", [])) == 1 else 0
        return template_bonus + simple_bonus + clean_text_bonus, folder.stat().st_mtime
    except (OSError, ValueError, TypeError):
        return None


def find_template(root: Path) -> Path:
    candidates = [(score, folder) for folder in root.iterdir() if folder.is_dir() and (score := _draft_score(folder))]
    if not candidates:
        raise RuntimeError("Không tìm thấy project mẫu có video và text track")
    return max(candidates, key=lambda item: item[0])[1]


def _capcut_pids() -> list[int]:
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pids: list[int] = []
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) >= 2 and row[0].lower() == "capcut.exe":
                try:
                    pids.append(int(row[1]))
                except ValueError:
                    pass
        return pids
    except OSError:
        return []


def _visible_window_pids() -> set[int]:
    if sys.platform != "win32":
        return set()
    visible: set[int] = set()
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def collect(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            visible.add(int(pid.value))
        return True

    user32.EnumWindows(collect, 0)
    return visible


def ensure_capcut_closed(logger: Callable[[str], None]) -> None:
    pids = _capcut_pids()
    if not pids:
        return
    if set(pids) & _visible_window_pids():
        raise RuntimeError("Hãy đóng cửa sổ CapCut trước khi tạo và đồng bộ project")

    logger("CapCut đã đóng; đang dọn tiến trình nền còn sót...")
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(0.5)
    if _capcut_pids():
        raise RuntimeError("Không thể dừng tiến trình CapCut chạy nền. Hãy kết thúc CapCut trong Task Manager rồi thử lại.")


def _safe_project_name(value: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .")
    return clean[:80] or f"HHVietSub-{time.strftime('%Y%m%d-%H%M%S')}"


def _upgrade_capcut9_schema(project: Path) -> None:
    """Wrap capcut-cli's portable timeline in the native CapCut 9 draft envelope."""
    now_us = int(time.time() * 1_000_000)
    platform = {
        "os": "windows", "os_version": "10.0", "app_id": 359289,
        "app_version": "9.0.0", "app_source": "cc", "device_id": "",
        "hard_disk_id": "", "mac_address": "",
    }
    config = {
        "video_mute": False, "record_audio_last_index": 1,
        "extract_audio_last_index": 1, "original_sound_last_index": 1,
        "subtitle_recognition_id": "", "subtitle_taskinfo": [],
        "lyrics_recognition_id": "", "lyrics_taskinfo": [],
        "subtitle_sync": True, "lyrics_sync": True, "voice_change_sync": False,
        "sticker_max_index": 1, "adjust_max_index": 1, "material_save_mode": 0,
        "export_range": None, "maintrack_adsorb": True, "combination_max_index": 1,
        "attachment_info": [], "zoom_info_params": None, "system_font_list": [],
        "multi_language_mode": "none", "multi_language_main": "none",
        "multi_language_current": "none", "multi_language_list": [],
        "subtitle_keywords_config": None, "use_float_render": False,
    }
    defaults: dict[str, Any] = {
        "version": 360000, "new_version": "177.0.0", "create_time": 0,
        "update_time": now_us, "is_drop_frame_timecode": False, "color_space": -1,
        "config": config, "group_container": None,
        "keyframes": {key: [] for key in ("videos", "audios", "texts", "stickers", "filters", "adjusts", "handwrites", "effects")},
        "keyframe_graph_list": None, "last_modified_platform": platform,
        "mutable_config": None, "cover": None, "retouch_cover": None,
        "relationships": None, "mixed_track_mode_on": False,
        "render_index_track_mode_on": True, "free_render_index_mode_on": False,
        "static_cover_image_path": "", "source": "default", "time_marks": None,
        "path": "", "lyrics_effects": None,
        "uneven_animation_template_info": {"composition": "", "content": "", "order": "", "sub_template_info_list": []},
        "draft_type": "video", "smart_ads_info": {"page_from": "", "routine": "", "draft_url": ""},
        "function_assistant_info": {},
    }
    content_path = project / "draft_content.json"
    data = json.loads(content_path.read_text(encoding="utf-8"))
    data["id"] = str(data.get("id") or uuid.uuid4()).upper()
    data["name"] = str(data.get("name") or project.name)
    data["platform"] = platform
    for key, value in defaults.items():
        data.setdefault(key, value)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    content_path.write_text(payload, encoding="utf-8")
    info_path = project / "draft_info.json"
    if info_path.exists():
        info_path.write_text(payload, encoding="utf-8")


def _finalize_native_metadata(project: Path, duration: int) -> None:
    now_us = int(time.time() * 1_000_000)
    meta_path = project / "draft_meta_info.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["draft_name"] = project.name
    meta["draft_id"] = str(meta.get("draft_id") or uuid.uuid4())
    meta["draft_fold_path"] = project.as_posix()
    meta["draft_root_path"] = project.parent.as_posix()
    meta["draft_json_file"] = (project / "draft_content.json").as_posix()
    meta["tm_duration"] = int(duration)
    meta["tm_draft_modified"] = now_us
    meta["draft_timeline_materials_size"] = sum(
        item.stat().st_size for item in project.iterdir() if item.is_file()
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _replace_video(project: Path, video: Path, logger: Callable[[str], None]) -> int:
    draft_path, mirrors = resolve_project_draft_paths(project)
    data = load_draft_json(draft_path, require_tracks=True)
    duration = _ffprobe_duration_us(video)
    if duration <= 0:
        raise RuntimeError("Không đọc được thời lượng video gốc")
    video_tracks = [track for track in data.get("tracks", []) if isinstance(track, dict) and track.get("type") == "video" and track.get("segments")]
    if not video_tracks:
        raise RuntimeError("Project mẫu không có video track")
    track = video_tracks[0]
    segment = track["segments"][0]
    track["segments"] = [segment]
    material_id = str(segment.get("material_id", ""))
    materials = data.setdefault("materials", {})
    video_materials = materials.get("videos", [])
    material = next((item for item in video_materials if str(item.get("id", "")) == material_id), None)
    if not material:
        raise RuntimeError("Không tìm thấy material video trong project mẫu")
    old_path = str(material.get("path", ""))
    material["path"] = video.as_posix()
    material["media_path"] = ""
    material["material_name"] = video.name
    material["duration"] = duration
    material["has_audio"] = True
    segment["source_timerange"] = {"start": 0, "duration": duration}
    segment["target_timerange"] = {"start": 0, "duration": duration}
    segment["speed"] = 1.0
    data["duration"] = duration
    save_project_drafts(draft_path, mirrors, data)
    meta_path = project / "draft_meta_info.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["draft_id"] = str(uuid.uuid4()).upper()
        meta["tm_duration"] = duration
        def patch(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    if isinstance(value, str) and old_path and value.replace("\\", "/") == old_path.replace("\\", "/"):
                        node[key] = video.as_posix()
                    else:
                        patch(value)
            elif isinstance(node, list):
                for value in node:
                    patch(value)
        patch(meta)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    logger(f"Đã thay video gốc: {video.name} · {duration / 1_000_000:.2f} giây")
    return duration


def validate_inputs(video: Path, srt: Path, voice_dir: Path) -> dict[str, Any]:
    if not video.is_file():
        raise ValueError("Video gốc không tồn tại")
    if not srt.is_file() or srt.suffix.lower() != ".srt":
        raise ValueError("File SRT không hợp lệ")
    if not voice_dir.is_dir():
        raise ValueError("Thư mục voice không tồn tại")
    cues = _collect_srt_segments(srt)
    found = []
    missing = []
    for index in range(1, len(cues) + 1):
        matches = [voice_dir / f"{index:04d}{ext}" for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg")]
        matches += [voice_dir / f"{index}{ext}" for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg")]
        match = next((item for item in matches if item.is_file()), None)
        (found if match else missing).append(str(match) if match else index)
    return {"subtitles": len(cues), "voiceFiles": len(found), "missing": missing, "ready": not missing}


def validate_existing_inputs(project: Path, srt: Path, voice_dir: Path) -> dict[str, Any]:
    if not project.is_dir() or not (project / "draft_content.json").is_file():
        raise ValueError("Dự án CapCut đã chọn không hợp lệ")
    # Reuse the proven SRT ↔ numbered voice validation without requiring a video file.
    if not srt.is_file() or srt.suffix.lower() != ".srt":
        raise ValueError("File SRT không hợp lệ")
    if not voice_dir.is_dir():
        raise ValueError("Thư mục voice không tồn tại")
    cues = _collect_srt_segments(srt)
    missing = []
    found = []
    for index in range(1, len(cues) + 1):
        candidates = [voice_dir / f"{index:04d}{ext}" for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg")]
        candidates += [voice_dir / f"{index}{ext}" for ext in (".wav", ".mp3", ".flac", ".m4a", ".ogg")]
        match = next((item for item in candidates if item.is_file()), None)
        (found if match else missing).append(str(match) if match else index)
    return {"subtitles": len(cues), "voiceFiles": len(found), "missing": missing, "ready": not missing,
            "projectName": project.name, "projectPath": str(project)}


def sync_existing_project(project: Path, srt: Path, voice_dir: Path,
                          logger: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Add SRT voices to an existing draft, preserving a recoverable JSON snapshot."""
    log = logger or (lambda _message: None)
    ensure_capcut_closed(log)
    analysis = validate_existing_inputs(project, srt, voice_dir)
    if analysis["missing"]:
        preview = ", ".join(f"{value:04d}" for value in analysis["missing"][:12])
        raise RuntimeError(f"Thiếu {len(analysis['missing'])} file voice: {preview}")
    draft_path, mirrors = resolve_project_draft_paths(project)
    # Keep a timestamped snapshot inside the project. Only JSON metadata is copied;
    # source videos/audio remain untouched and are referenced by path.
    backup_dir = project / f"HHVietSub_Backup_{time.strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=False, exist_ok=False)
    for source in {draft_path, *mirrors, project / "draft_meta_info.json"}:
        if source.is_file():
            shutil.copy2(source, backup_dir / source.name)
    log(f"Đã sao lưu draft: {backup_dir.name}")
    try:
        data = load_draft_json(draft_path, require_tracks=True)
        srt_segments = _collect_srt_segments(srt)
        _apply_srt_to_existing_text_track(data, srt_segments, log)
        save_project_drafts(draft_path, mirrors, data)
        log(f"Đã cập nhật {len(srt_segments)} dòng phụ đề trên dự án có sẵn")
        import_result = import_voice_files_by_subtitles(project, voice_dir, srt_path=srt, backup=False, logger=log)
        cut_result = cut_video_by_subtitles_only(project, backup=False, logger=log, srt_path=srt)
        sync_result = retime_video_subtitle_segments_to_audio(project, backup=False, logger=log,
                                                               use_audio_timing=True, srt_path=srt)
        normalize_project_metadata(project, log)
        final_draft, _ = resolve_project_draft_paths(project)
        final_data = load_draft_json(final_draft, require_tracks=True)
        final_duration = int(final_data.get("duration", 0))
        _finalize_native_metadata(project, final_duration)
        _patch_root_registration(project_root(), project, duration=final_duration)
        return {"projectName": project.name, "projectPath": str(project), "template": "Dự án có sẵn",
                "backupPath": str(backup_dir), "analysis": analysis, "import": import_result,
                "cut": cut_result, "sync": sync_result}
    except Exception:
        log(f"Đồng bộ lỗi; bản sao an toàn nằm tại {backup_dir}")
        raise


def _patch_root_registration(root: Path, target: Path, remove: bool = False, duration: int = 0) -> None:
    index_path = root / "root_meta_info.json"
    if not index_path.exists():
        return
    data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    target_norm = target.as_posix().lower()
    changed = False
    def visit(node: Any) -> None:
        nonlocal changed
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            kept = []
            for item in node:
                fold = str(item.get("draft_fold_path", "")).replace("\\", "/").lower() if isinstance(item, dict) else ""
                if fold == target_norm:
                    changed = True
                    if remove:
                        continue
                    item["tm_duration"] = int(duration)
                    item["tm_draft_modified"] = int(time.time() * 1_000_000)
                visit(item)
                kept.append(item)
            node[:] = kept
    visit(data)
    if changed:
        backup = index_path.with_suffix(".json.hhvietsub.bak")
        shutil.copy2(index_path, backup)
        temporary = index_path.with_suffix(".json.hhvietsub.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(index_path)


def create_project(video: Path, srt: Path, voice_dir: Path, name: str,
                   logger: Callable[[str], None] | None = None) -> dict[str, Any]:
    log = logger or (lambda _message: None)
    ensure_capcut_closed(log)
    analysis = validate_inputs(video, srt, voice_dir)
    if analysis["missing"]:
        preview = ", ".join(f"{value:04d}" for value in analysis["missing"][:12])
        raise RuntimeError(f"Thiếu {len(analysis['missing'])} file voice: {preview}")
    root = project_root()
    project_name = _safe_project_name(name)
    target = root / project_name
    if target.exists():
        raise RuntimeError(f"Project đã tồn tại: {project_name}")
    project_root_path = Path(__file__).resolve().parents[2]
    cli = project_root_path / "vendor" / "capcut-cli" / "dist" / "index.js"
    if not cli.is_file():
        raise RuntimeError("Thiếu bộ tạo project mới capcut-cli")
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    ffprobe_candidates = [
        project_root_path / "vendor" / "ffprobe.exe",
        Path(r"D:\Tool\CapCutBatchStudio\node_modules\ffprobe-static\bin\win32\x64\ffprobe.exe"),
    ]
    ffprobe = next((candidate for candidate in ffprobe_candidates if candidate.is_file()), None)
    command = [str(node), str(cli), "quickstart", project_name, "--video", str(video), "--srt", str(srt), "--drafts", str(root)]
    if ffprobe:
        command.extend(["--ffprobe-cmd", str(ffprobe)])
    log("Khởi tạo draft CapCut mới từ schema sạch…")
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"capcut-cli lỗi {completed.returncode}")
        created = json.loads(completed.stdout)
        if not created.get("registered"):
            raise RuntimeError("Draft đã tạo nhưng chưa đăng ký được vào danh sách project CapCut")
        log(f"Đã tạo draft mới và đăng ký vào CapCut: {project_name}")
        _upgrade_capcut9_schema(target)
        import_result = import_voice_files_by_subtitles(target, voice_dir, srt_path=srt, backup=False, logger=log)
        cut_result = cut_video_by_subtitles_only(target, backup=False, logger=log, srt_path=srt)
        sync_result = retime_video_subtitle_segments_to_audio(target, backup=False, logger=log,
                                                               use_audio_timing=True, srt_path=srt)
        normalize_project_metadata(target, log)
        draft_path, _ = resolve_project_draft_paths(target)
        final_data = load_draft_json(draft_path, require_tracks=True)
        final_duration = int(final_data.get("duration", 0))
        _finalize_native_metadata(target, final_duration)
        _patch_root_registration(root, target, duration=final_duration)
        return {"projectName": project_name, "projectPath": str(target), "template": "Schema mới (capcut-cli)",
                "analysis": analysis, "import": import_result, "cut": cut_result, "sync": sync_result}
    except Exception:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        _patch_root_registration(root, target, remove=True)
        raise
