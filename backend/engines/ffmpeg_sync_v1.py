from __future__ import annotations

import json
import hashlib
import math
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any, Callable

TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _safe_log(logger: Callable[[str], None] | None, message: str) -> None:
    if not logger:
        return
    try:
        logger(message)
    except Exception:
        try:
            logger(message.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def _seconds(value: str) -> float:
    match = TIME_RE.search(value.strip())
    if not match:
        raise ValueError(f"Mốc thời gian SRT không hợp lệ: {value}")
    hour, minute, second, millis = (int(part) for part in match.groups())
    return hour * 3600 + minute * 60 + second + millis / (1000 if len(match.group(4)) <= 3 else 10 ** len(match.group(4)))


def _stamp(value: float) -> str:
    millis = max(0, round(value * 1000))
    hour, millis = divmod(millis, 3_600_000)
    minute, millis = divmod(millis, 60_000)
    second, millis = divmod(millis, 1000)
    return f"{hour:02d}:{minute:02d}:{second:02d},{millis:03d}"


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    cues: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip("\ufeff") for line in block.splitlines()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        left, right = lines[timing_index].split("-->", 1)
        cues.append({"id": len(cues) + 1, "start": _seconds(left), "end": _seconds(right), "text": "\n".join(lines[timing_index + 1:]).strip()})
    if not cues:
        raise ValueError("File SRT không có câu hợp lệ")
    return cues


def _get_sorted_audio_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    valid_exts = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac"}
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in valid_exts]
    def natural_key(p: Path):
        numbers = re.findall(r'\d+', p.stem)
        return [int(n) for n in numbers] if numbers else [p.stem]
    return sorted(files, key=natural_key)


def _voice_path(folder: Path, index: int, sorted_audio: list[Path] | None = None) -> Path | None:
    valid_exts = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac")
    stems = (
        f"{index:04d}", f"{index:05d}", f"{index:03d}", str(index),
        f"dich_capcut_voice_{index:04d}", f"dich_capcut_voice_{index}",
        f"voice_{index:04d}", f"voice_{index}",
        f"audio_{index:04d}", f"audio_{index}",
    )
    for stem in stems:
        for ext in valid_exts:
            candidate = folder / f"{stem}{ext}"
            if candidate.is_file():
                return candidate

    str_idx_4 = f"{index:04d}"
    str_idx = str(index)
    for ext in valid_exts:
        for f in folder.glob(f"*{ext}"):
            stem = f.stem
            if stem.endswith(f"_{str_idx_4}") or stem.endswith(f"_{str_idx}") or stem.endswith(f"-{str_idx_4}") or stem.endswith(f"-{str_idx}"):
                return f

    audio_list = sorted_audio if sorted_audio is not None else _get_sorted_audio_files(folder)
    if audio_list and 1 <= index <= len(audio_list):
        return audio_list[index - 1]

    return None


def _probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Không đọc được thời lượng: {path.name}")
    return float(result.stdout.strip())


def _audio_duration(ffprobe: str, path: Path) -> float:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as audio:
                return audio.getnframes() / max(1, audio.getframerate())
        except (wave.Error, OSError):
            pass
    return _probe_duration(ffprobe, path)


def find_tools() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        package_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        if package_root.is_dir():
            ffmpeg_path = next(package_root.glob("**/bin/ffmpeg.exe"), None)
            ffprobe_path = next(package_root.glob("**/bin/ffprobe.exe"), None)
            ffmpeg = str(ffmpeg_path) if ffmpeg_path else None
            ffprobe = str(ffprobe_path) if ffprobe_path else None
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Chưa cài FFmpeg. Vui lòng cài FFmpeg bằng winget install Gyan.FFmpeg")
    return ffmpeg, ffprobe


def validate_inputs(video: Path, srt: Path, voice_dir: Path, voice_speed: float = 1.0) -> dict[str, Any]:
    if not video.is_file(): raise ValueError("Video gốc không tồn tại")
    if not srt.is_file(): raise ValueError("File SRT không tồn tại")
    if not voice_dir.is_dir(): raise ValueError("Thư mục voice không tồn tại")
    cues = parse_srt(srt)
    sorted_audio = _get_sorted_audio_files(voice_dir)
    voices = [_voice_path(voice_dir, cue["id"], sorted_audio) for cue in cues]
    missing = [cue["id"] for cue, voice in zip(cues, voices) if voice is None]
    try:
        find_tools(); ffmpeg_ready = True
    except RuntimeError:
        ffmpeg_ready = False

    raw_duration = 0.0
    if not missing and ffmpeg_ready:
        _, ffprobe = find_tools()
        raw_duration = sum(_audio_duration(ffprobe, v) for v in voices if v is not None)

    safe_speed = max(0.1, voice_speed)
    adjusted_duration = raw_duration / safe_speed

    return {
        "subtitles": len(cues),
        "voiceFiles": len(cues) - len(missing),
        "missing": missing,
        "ready": not missing and ffmpeg_ready,
        "ffmpegReady": ffmpeg_ready,
        "rawVoiceDuration": round(raw_duration, 2),
        "totalVoiceDuration": round(adjusted_duration, 2),
        "voiceSpeed": voice_speed,
    }


def _run(command: list[str], description: str, timeout: float | None = None) -> None:
    if "-nostdin" not in command:
        command = [command[0], "-nostdin", *command[1:]]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        limit = round(float(timeout or 0))
        raise RuntimeError(
            f"{description}: FFmpeg không tiến triển và đã được dừng sau {limit} giây. "
            "Có thể chạy lại; các cụm hoàn thành trước đó sẽ được giữ lại."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"{description}: {(result.stderr or result.stdout)[-1600:]}")


def _encoder(ffmpeg: str, preferred: str = "auto") -> list[str]:
    result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    encoders_out = result.stdout.lower()

    pref = preferred.lower()
    candidates: list[str] = []
    if pref in ("nvenc", "h264_nvenc"):
        candidates = ["h264_nvenc"]
    elif pref in ("amf", "h264_amf"):
        candidates = ["h264_amf"]
    elif pref in ("qsv", "h264_qsv"):
        candidates = ["h264_qsv"]
    elif pref in ("x264", "libx264", "cpu"):
        candidates = ["libx264"]
    else:
        candidates = ["h264_nvenc", "h264_amf", "h264_qsv"]

    for enc in candidates:
        if enc in encoders_out:
            if enc == "h264_nvenc":
                probe = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=size=256x256:duration=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode == 0:
                    return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
            elif enc == "h264_amf":
                probe = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=size=256x256:duration=0.1", "-c:v", "h264_amf", "-f", "null", "-"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode == 0:
                    return ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_p", "23", "-qp_i", "23"]
            elif enc == "h264_qsv":
                probe = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=size=256x256:duration=0.1", "-c:v", "h264_qsv", "-f", "null", "-"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode == 0:
                    return ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"]

    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "4"]


def _has_audio(ffprobe: str, path: Path) -> bool:
    result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode == 0 and "audio" in result.stdout


def _video_frame_rate(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    value = result.stdout.strip()
    try:
        numerator, denominator = value.split("/", 1)
        fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        fps = 25.0
    return max(1.0, min(240.0, fps))


def _atempo_chain(rate: float) -> str:
    rate = max(0.03125, min(32.0, rate))
    values: list[float] = []
    while rate < 0.5:
        values.append(0.5); rate /= 0.5
    while rate > 2.0:
        values.append(2.0); rate /= 2.0
    values.append(rate)
    return ",".join(f"atempo={value:.9f}" for value in values)


def _render_group_piecewise(
    ffmpeg: str, ffprobe: str, video: Path, chunk: Path, group: list[dict[str, Any]],
    source_fps: float, encoder: list[str], keep_original_audio: bool,
    expected_duration: float, log: Callable[[str], None] | None,
) -> None:
    """Reliable fallback that avoids multi-branch filter concat deadlocks."""
    parts_dir = chunk.parent / f"{chunk.stem}-parts"
    if parts_dir.exists():
        shutil.rmtree(parts_dir)
    parts_dir.mkdir(parents=True, exist_ok=True)
    part_paths: list[Path] = []
    try:
        for index, piece in enumerate(group, 1):
            _safe_log(log, f"Chế độ an toàn: đang render đoạn {index}/{len(group)} của cụm {chunk.stem.replace('chunk-', '')}")
            source_start = float(piece["sourceStart"])
            source_duration = max(0.001, float(piece["source"]))
            target_duration = max(0.001, float(piece["target"]))
            factor = target_duration / source_duration
            part = parts_dir / f"part-{index:03d}.mp4"
            part_paths.append(part)
            filters = [
                f"[0:v]setpts=N/({source_fps:.9f}*TB),trim=duration={source_duration:.6f},"
                f"setpts=(PTS-STARTPTS)*{factor:.9f},format=yuv420p[vout]"
            ]
            if keep_original_audio:
                tempo = source_duration / target_duration
                filters.append(
                    f"[0:a]atrim=duration={source_duration:.6f},asetpts=PTS-STARTPTS,"
                    f"{_atempo_chain(tempo)},apad,atrim=duration={target_duration:.6f},"
                    "asetpts=PTS-STARTPTS[aout]"
                )
            command = [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-filter_complex_threads", "1",
                "-ss", f"{source_start:.6f}", "-t", f"{source_duration + 0.5:.6f}",
                "-i", str(video), "-filter_complex", ";".join(filters),
                "-map", "[vout]", *encoder,
            ]
            command += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"] if keep_original_audio else ["-an"]
            command += ["-t", f"{target_duration:.6f}", str(part)]
            _run(command, f"Không render được đoạn dự phòng {index}/{len(group)}", timeout=max(60.0, target_duration * 10.0))
        concat_list = parts_dir / "parts.txt"
        concat_list.write_text("\n".join(f"file '{str(path).replace(chr(39), chr(39)*2)}'" for path in part_paths), encoding="utf-8")
        _run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy",
            *([] if keep_original_audio else ["-an"]),
            "-movflags", "+faststart", str(chunk),
        ], "Không nối được các đoạn dự phòng", timeout=90)
        if not _valid_media(ffprobe, chunk, require_audio=keep_original_audio, expected_duration=expected_duration):
            raise RuntimeError("Chunk dự phòng hoàn tất nhưng thời lượng không hợp lệ")
    finally:
        shutil.rmtree(parts_dir, ignore_errors=True)


def _valid_media(ffprobe: str, path: Path, require_audio: bool = False,
                 expected_duration: float | None = None) -> bool:
    if not path.is_file() or path.stat().st_size <= 1024:
        return False
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0 or not result.stdout.strip() or (require_audio and not _has_audio(ffprobe, path)):
        return False
    if expected_duration is not None:
        try:
            actual_duration = float(result.stdout.strip())
        except ValueError:
            return False
        if abs(actual_duration - expected_duration) > 0.5:
            return False
    return True


def _group_signature(video: Path, group: list[dict[str, Any]], keep_original_audio: bool) -> str:
    stat = video.stat()
    payload = {
        "version": 5,
        "video": str(video),
        "videoSize": stat.st_size,
        "videoModifiedNs": stat.st_mtime_ns,
        "originalAudio": keep_original_audio,
        "pieces": group,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_pcm24k_frames(ffmpeg: str, path: Path, sample_rate: int = 24000,
                        voice_speed: float = 1.0, change_pitch: bool = False) -> bytes:
    """Decode any audio format (WAV, MP3, FLAC, M4A, OGG) to 16-bit mono PCM 24000Hz via FFmpeg with speed & pitch adjustment."""
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", str(path),
    ]
    if abs(voice_speed - 1.0) > 0.001:
        if change_pitch:
            target_rate = round(sample_rate * voice_speed)
            command += ["-af", f"asetrate={target_rate},aresample={sample_rate}"]
        else:
            command += ["-af", _atempo_chain(voice_speed)]
    command += ["-f", "s16le", "-ac", "1", "-ar", str(sample_rate), "-"]

    result = subprocess.run(
        command, capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    if result.returncode != 0:
        raise RuntimeError(f"Không giải mã được audio {path.name}: {result.stderr.decode('utf-8', errors='replace')}")
    return result.stdout


def _write_master_timeline(ffmpeg: str, path: Path, subtitles: list[dict[str, Any]], total_duration: float,
                            sample_rate: int = 24000, voice_speed: float = 1.0, change_pitch: bool = False) -> None:
    """Place every voice file (WAV, MP3, FLAC, M4A, OGG) at its mapped subtitle start time."""
    silence = b"\x00\x00" * sample_rate
    cursor = 0
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(sample_rate)
        for subtitle in subtitles:
            target_start = round(float(subtitle["startNew"]) * sample_rate)
            remaining = max(0, target_start - cursor)
            while remaining:
                count = min(remaining, sample_rate)
                output.writeframesraw(silence[:count * 2])
                remaining -= count
                cursor += count
            voice_path = Path(subtitle["voice"])
            frames = _read_pcm24k_frames(ffmpeg, voice_path, sample_rate, voice_speed=voice_speed, change_pitch=change_pitch)
            output.writeframesraw(frames)
            cursor += len(frames) // 2
        total_frames = round(total_duration * sample_rate)
        remaining = max(0, total_frames - cursor)
        while remaining:
            count = min(remaining, sample_rate)
            output.writeframesraw(silence[:count * 2])
            remaining -= count
            cursor += count


def _cleanup_success_artifacts(chunks_dir: Path, concat_file: Path, plan_path: Path,
                               log: Callable[[str], None]) -> None:
    """Remove render intermediates only after the final output is complete."""
    removed: list[str] = []
    try:
        if chunks_dir.is_dir():
            shutil.rmtree(chunks_dir)
            removed.append("chunks")
        for path in (concat_file, plan_path):
            if path.exists():
                path.unlink()
                removed.append(path.name)
    except OSError as exc:
        _safe_log(log, f"Cảnh báo: không dọn hết file tạm: {exc}")
        return
    if removed:
        _safe_log(log, "Đã dọn file tạm; chỉ giữ MP4, SRT, master voice và video-synced.mp4")


def render(video: Path, srt: Path, voice_dir: Path, output_dir: Path, name: str,
           logger: Callable[[str], None] | None = None, chunk_pieces: int = 100, encoder_choice: str = "auto",
           voice_speed: float = 1.0, change_pitch: bool = False, video_volume_db: float = -20.0,
           merge_audio: bool = True) -> dict[str, Any]:
    log = logger or (lambda _message: None)
    video, srt, voice_dir, output_dir = video.resolve(), srt.resolve(), voice_dir.resolve(), output_dir.resolve()
    ffmpeg, ffprobe = find_tools()
    analysis = validate_inputs(video, srt, voice_dir, voice_speed=voice_speed)
    if analysis["missing"]: raise RuntimeError(f"Thiếu {len(analysis['missing'])} file voice")
    safe_name = re.sub(r'[<>:"/\\|?*]+', "-", name).strip(" .") or f"HHVietSub-FFmpeg-{int(time.time())}"
    target = (output_dir / safe_name).resolve()
    chunks_dir = target / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    cues = parse_srt(srt)
    sorted_audio = _get_sorted_audio_files(voice_dir)
    video_duration = _probe_duration(ffprobe, video)
    source_fps = _video_frame_rate(ffprobe, video)
    keep_original_audio = _has_audio(ffprobe, video)
    cue_audio: list[dict[str, Any]] = []
    stretch_intervals: list[dict[str, Any]] = []
    stretch_cursor = 0.0
    safe_speed = max(0.1, voice_speed)
    for cue in cues:
        start = max(stretch_cursor, min(video_duration, float(cue["start"])))
        end = max(start + 0.001, min(video_duration, float(cue["end"])))
        voice = _voice_path(voice_dir, cue["id"], sorted_audio)
        assert voice is not None
        voice_duration = _audio_duration(ffprobe, voice) / safe_speed
        source_duration = end - start
        cue_audio.append({**cue, "voice": str(voice), "voiceDuration": voice_duration})
        if voice_duration > source_duration + 0.02:
            stretch_intervals.append({"kind": "voice", "sourceStart": start, "sourceEnd": end, "source": source_duration, "target": voice_duration, "voiceDuration": voice_duration, "voice": str(voice), "id": cue["id"]})
            stretch_cursor = end

    _safe_log(log, f"Đã quét {len(cues)} câu: {len(stretch_intervals)} câu voice dài hơn SRT cần cắt và làm chậm video (Tốc độ voice: {voice_speed:.2f}x, Đổi cao độ: {change_pitch}, Âm gốc: {video_volume_db:.0f}dB)")

    pieces: list[dict[str, Any]] = []
    source_cursor = target_cursor = 0.0
    for stretch in stretch_intervals:
        start, end = float(stretch["sourceStart"]), float(stretch["sourceEnd"])
        if start > source_cursor + 0.001:
            duration = start - source_cursor
            pieces.append({"kind": "gap", "sourceStart": source_cursor, "sourceEnd": start, "source": duration, "target": duration})
            target_cursor += duration
        pieces.append(stretch)
        source_cursor = end
        target_cursor += float(stretch["target"])
    if source_cursor < video_duration:
        duration = video_duration - source_cursor
        pieces.append({"kind": "gap", "sourceStart": source_cursor, "sourceEnd": video_duration, "source": duration, "target": duration})
        target_cursor += duration

    def map_time(source_time: float) -> float:
        offset = 0.0
        for stretch in stretch_intervals:
            start, end = float(stretch["sourceStart"]), float(stretch["sourceEnd"])
            target_duration = float(stretch["target"])
            if source_time <= start:
                return source_time + offset
            if source_time < end:
                ratio = (source_time - start) / max(0.001, end - start)
                return start + offset + ratio * target_duration
            offset += target_duration - (end - start)
        return source_time + offset

    updated: list[dict[str, Any]] = []
    voice_cursor = 0.0
    for cue in cue_audio:
        mapped_start = max(voice_cursor, map_time(float(cue["start"])))
        mapped_end = mapped_start + float(cue["voiceDuration"])
        updated.append({**cue, "startNew": mapped_start, "endNew": mapped_end})
        voice_cursor = mapped_end

    plan_path = target / "sync-plan.json"
    plan_path.write_text(json.dumps({"source": str(video), "duration": target_cursor, "pieces": pieces, "subtitles": updated, "originalAudio": {"enabled": keep_original_audio, "volumeDb": video_volume_db}, "voiceSpeed": voice_speed, "changePitch": change_pitch}, ensure_ascii=False, indent=2), encoding="utf-8")
    output_srt = target / f"{safe_name}.srt"
    output_srt.write_text("\n\n".join(f"{i}\n{_stamp(cue['startNew'])} --> {_stamp(cue['endNew'])}\n{cue['text']}" for i, cue in enumerate(updated, 1)) + "\n", encoding="utf-8")
    master_voice = target / f"{safe_name}.voice.wav"
    _safe_log(log, f"Đang ghép master voice (hỗ trợ MP3/WAV/FLAC/M4A) với tốc độ {voice_speed:.2f}x (Cao độ: {'thay đổi' if change_pitch else 'giữ nguyên'})…")
    _write_master_timeline(ffmpeg, master_voice, updated, target_cursor, voice_speed=voice_speed, change_pitch=change_pitch)

    # Pieces are rendered sequentially, so a larger group no longer increases
    # filter RAM. Twelve pieces reduces concat/container overhead while keeping
    # cache checkpoints reasonably frequent.
    effective_chunk_pieces = min(24, max(2, chunk_pieces))
    groups = [pieces[i:i + effective_chunk_pieces] for i in range(0, len(pieces), effective_chunk_pieces)]
    encoder = _encoder(ffmpeg, encoder_choice)
    chunk_paths: list[Path] = []
    # Always use the bounded one-piece pipeline. The former split/asplit graph
    # could buffer enough decoded HD frames to exhaust 32 GB RAM.
    piecewise_mode = True
    for group_index, group in enumerate(groups, 1):
        chunk = chunks_dir / f"chunk-{group_index:04d}.mp4"; chunk_paths.append(chunk)
        signature_path = chunk.with_suffix(".signature")
        expected_signature = _group_signature(video, group, keep_original_audio)
        expected_group_duration = sum(float(piece["target"]) for piece in group)
        cached_signature = signature_path.read_text(encoding="ascii", errors="ignore").strip() if signature_path.is_file() else ""
        media_is_valid = _valid_media(
            ffprobe, chunk, require_audio=keep_original_audio,
            expected_duration=expected_group_duration,
        )
        if (cached_signature == expected_signature or not cached_signature) and media_is_valid:
            if not cached_signature:
                signature_path.write_text(expected_signature, encoding="ascii")
                piecewise_mode = True
                _safe_log(log, f"Đã phục hồi cache hợp lệ cho cụm {group_index}")
            _safe_log(log, f"Bỏ qua cụm {group_index}/{len(groups)} đã hoàn thành")
            continue
        source_start, source_end = group[0]["sourceStart"], group[-1]["sourceEnd"]
        video_sources = "".join(f"[vsrc{index}]" for index in range(len(group)))
        filters = [f"[0:v]setpts=N/({source_fps:.9f}*TB),split={len(group)}{video_sources}"]
        if keep_original_audio:
            audio_sources = "".join(f"[asrc{index}]" for index in range(len(group)))
            filters.append(f"[0:a]asetpts=N/SR/TB,asplit={len(group)}{audio_sources}")
        labels = []
        for index, piece in enumerate(group):
            local_start = piece["sourceStart"] - source_start; local_end = piece["sourceEnd"] - source_start
            factor = piece["target"] / max(piece["source"], 0.001)
            filters.append(f"[vsrc{index}]trim=start={local_start:.6f}:end={local_end:.6f},setpts=(PTS-STARTPTS)*{factor:.9f}[v{index}]")
            if keep_original_audio:
                tempo = piece["source"] / max(piece["target"], 0.001)
                # Timestamps are already rebased before atempo. Using async
                # resampling on 10-20 split branches can make FFmpeg 8.x wait
                # forever at concat (observed on long projects around chunk 96).
                filters.append(
                    f"[asrc{index}]atrim=start={local_start:.6f}:end={local_end:.6f},"
                    f"asetpts=PTS-STARTPTS,{_atempo_chain(tempo)},"
                    f"apad,atrim=duration={float(piece['target']):.6f},asetpts=PTS-STARTPTS[a{index}]"
                )
                labels.append(f"[v{index}][a{index}]")
            else:
                labels.append(f"[v{index}]")
        if keep_original_audio:
            filters.append("".join(labels) + f"concat=n={len(group)}:v=1:a=1[vcat][aout];[vcat]format=yuv420p[vout]")
        else:
            filters.append("".join(labels) + f"concat=n={len(group)}:v=1:a=0,format=yuv420p[vout]")
        script = chunks_dir / f"chunk-{group_index:04d}.filter"
        script.write_text(";\n".join(filters), encoding="utf-8")
        
        progress_info = {
            "currentChunk": group_index,
            "totalChunks": len(groups),
            "percent": round((group_index / len(groups)) * 100),
            "message": f"Đang co giãn hình ảnh: cụm {group_index}/{len(groups)} ({round((group_index / len(groups)) * 100)}%)"
        }
        _safe_log(log, json.dumps(progress_info, ensure_ascii=False))
        
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                   "-filter_complex_threads", "2", "-ss", f"{source_start:.6f}",
                   "-t", f"{source_end-source_start:.6f}", "-i", str(video),
                   "-filter_complex_script", str(script), "-map", "[vout]", *encoder]
        command += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"] if keep_original_audio else ["-an"]
        command += ["-t", f"{expected_group_duration:.6f}"]
        command.append(str(chunk))
        # A chunk is normally much faster than real time with GPU encoding.
        # Bound pathological filters/drivers so one chunk cannot hang forever.
        chunk_timeout = max(45.0, min(120.0, expected_group_duration * 2.5))
        try:
            if piecewise_mode:
                raise RuntimeError("đang dùng chế độ từng đoạn an toàn sau một cụm không ổn định")
            _run(command, f"Không render được cụm {group_index}", timeout=chunk_timeout)
        except RuntimeError as exc:
            piecewise_mode = True
            _safe_log(log, f"Cụm {group_index} không ổn định ({exc}). Chuyển sang render từng đoạn an toàn cho phần còn lại…")
            _render_group_piecewise(
                ffmpeg, ffprobe, video, chunk, group, source_fps, encoder,
                keep_original_audio, expected_group_duration, log,
            )
        signature_path.write_text(expected_signature, encoding="ascii")

    concat_file = target / "chunks.txt"
    concat_file.write_text("\n".join(f"file '{str(path).replace(chr(39), chr(39)*2)}'" for path in chunk_paths), encoding="utf-8")
    joined_video = target / "video-synced.mp4"
    _safe_log(log, "Đang nối các cụm video…")
    _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(joined_video)], "Không nối được video")
    joined_duration = _probe_duration(ffprobe, joined_video)
    allowed_drift = max(0.5, target_cursor * 0.001)
    if abs(joined_duration - target_cursor) > allowed_drift:
        raise RuntimeError(
            f"Video sau khi nối lệch {abs(joined_duration-target_cursor):.3f} giây "
            f"(video {joined_duration:.3f}s, kế hoạch {target_cursor:.3f}s). "
            "Không xuất file để tránh lệch voice/phụ đề."
        )
    if not merge_audio:
        (target / f"{safe_name}.mp4").unlink(missing_ok=True)
        _cleanup_success_artifacts(chunks_dir, concat_file, plan_path, log)
        _safe_log(log, "Hoàn tất bộ 3 file rời: video đồng bộ, phụ đề và master voice.")
        return {
            "projectName": safe_name, "projectPath": str(target), "outputDir": str(target),
            "template": f"FFmpeg · bộ 3 file rời · voice {voice_speed:.2f}x",
            "subtitles": len(cues), "pieces": len(pieces),
            "videoPath": str(joined_video), "subtitlePath": str(output_srt),
            "voicePath": str(master_voice), "merged": False,
        }
    final_path = target / f"{safe_name}.mp4"
    if keep_original_audio and video_volume_db > -35:
        _safe_log(log, f"Đang trộn voice với âm thanh video gốc ở {video_volume_db:.0f} dB…")
        audio_end = max(0.001, target_cursor)
        mix_filter = f"[0:a]volume={video_volume_db:.1f}dB[bg];[bg][1:a]amix=inputs=2:duration=longest:normalize=0,apad,atrim=start=0:end={audio_end:.6f}[aout]"
        _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(joined_video), "-i", str(master_voice), "-filter_complex", mix_filter, "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final_path)], "Không trộn được voice với âm thanh gốc")
        _cleanup_success_artifacts(chunks_dir, concat_file, plan_path, log)
        _safe_log(log, f"Hoàn tất: {final_path.name}")
        return {"projectName": safe_name, "projectPath": str(final_path), "outputDir": str(target), "template": f"FFmpeg · voice {voice_speed:.2f}x · âm gốc {video_volume_db:.0f}dB", "subtitles": len(cues), "pieces": len(pieces)}
    _safe_log(log, "Đang ghép video và master voice (tắt âm gốc)…")
    _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(joined_video), "-i", str(master_voice), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final_path)], "Không ghép được video cuối")
    _cleanup_success_artifacts(chunks_dir, concat_file, plan_path, log)
    _safe_log(log, f"Hoàn tất: {final_path.name}")
    return {"projectName": safe_name, "projectPath": str(final_path), "outputDir": str(target), "template": f"FFmpeg · voice {voice_speed:.2f}x · tắt âm gốc", "subtitles": len(cues), "pieces": len(pieces)}
