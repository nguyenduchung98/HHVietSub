from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Any, Callable


class VoiceStudioService:
    AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm"}
    MAX_REFERENCE_BYTES = 50 * 1024 * 1024
    MAX_TEXT_LENGTH = 100_000

    def __init__(
        self,
        user_data: Path,
        app_root: Path,
        omnivoice_root: Path,
        voice_config: Callable[[], dict[str, Any]],
        remote_generate: Callable[[str, str, dict[str, Any], Path], dict[str, Any]],
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.user_data = user_data.resolve()
        self.app_root = app_root.resolve()
        self.omnivoice_root = omnivoice_root.resolve()
        self.voices_dir = self.omnivoice_root / "voices"
        self.voice_config = voice_config
        self.remote_generate = remote_generate
        self.emit = emit or (lambda _event: None)
        self._history_lock = threading.Lock()
        self._runtime_lock = threading.Lock()
        self._runtime_process: subprocess.Popen[str] | None = None
        self._runtime_output: queue.Queue[str | None] | None = None

    def list_voices(self) -> list[dict[str, Any]]:
        voices: list[dict[str, Any]] = []
        if not self.voices_dir.is_dir():
            return voices
        profile_dirs: set[Path] = set()
        for profile_path in sorted(self.voices_dir.glob("*/profile.json")):
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                audio = self._profile_file(profile_path.parent, profile.get("ref_audio", ""))
                prompt = self._profile_file(profile_path.parent, profile.get("voice_prompt", "voice.pt"))
                profile_dirs.add(profile_path.parent)
                voices.append({
                    "id": profile_path.parent.name,
                    "name": str(profile.get("name") or profile_path.parent.name),
                    "language": normalize_language(profile.get("language")),
                    "ready": audio.is_file(),
                    "promptReady": prompt.is_file(),
                    "source": "OmniVoice",
                    "referenceAudio": str(audio) if audio.is_file() else None,
                })
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                logging.warning("Invalid voice profile %s: %s", profile_path, exc)
        for audio in sorted(self.voices_dir.iterdir()):
            if audio.is_file() and audio.suffix.lower() in self.AUDIO_EXTENSIONS:
                voices.append({"id": slugify(audio.stem), "name": audio.stem, "language": normalize_language(None),
                               "ready": False, "source": "Legacy audio", "referenceAudio": str(audio)})
        return voices

    def languages(self) -> list[dict[str, str]]:
        path = self.omnivoice_root / "docs" / "languages.md"
        languages: list[dict[str, str]] = [{"id": "auto", "name": "Tự động nhận diện"}]
        known = {"auto"}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                match = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
                if match:
                    name, language_id = match.group(1).strip(), match.group(2).strip()
                    if language_id and language_id not in known:
                        languages.append({"id": language_id, "name": name})
                        known.add(language_id)
        except OSError as exc:
            logging.warning("Cannot read OmniVoice language catalog: %s", exc)
        if len(languages) == 1:
            languages.extend({"id": code, "name": name} for code, name in (
                ("vi", "Vietnamese"), ("en", "English"), ("zh", "Chinese"), ("ja", "Japanese"),
                ("ko", "Korean"), ("es", "Spanish"), ("fr", "French"), ("de", "German")))
        return languages

    def create_voice(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", "")).strip()
        language = str(params.get("language", "auto")).strip() or "auto"
        ref_text = str(params.get("refText", "")).strip()
        notes = str(params.get("notes", "")).strip()
        if not name:
            raise ValueError("Vui lòng nhập tên giọng")
        if not bool(params.get("consentConfirmed")):
            raise ValueError("Bạn cần xác nhận quyền sử dụng giọng nói")
        audio_path = Path(str(params.get("audioPath", ""))).resolve()
        if not audio_path.is_file() or audio_path.suffix.lower() not in self.AUDIO_EXTENSIONS:
            raise ValueError("Audio tham chiếu không hợp lệ")
        if audio_path.stat().st_size > self.MAX_REFERENCE_BYTES:
            raise ValueError("Audio tham chiếu vượt quá 50 MB")
        destination = self._reserve_voice_dir(slugify(name))
        ref_name = f"ref{audio_path.suffix.lower()}"
        try:
            shutil.copy2(audio_path, destination / ref_name)
            self._atomic_text(destination / "ref_text.txt", ref_text)
            profile = {"name": name, "language": language, "ref_audio": ref_name, "ref_text_file": "ref_text.txt",
                       "voice_prompt": "voice.pt", "model": "k2-fsa/OmniVoice", "device": "auto",
                       "preprocess_prompt": False, "auto_transcribe": not bool(ref_text), "notes": notes,
                       "consent_confirmed": True, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            self._atomic_json(destination / "profile.json", profile)
            python = self.omnivoice_root / ".venv" / "Scripts" / "python.exe"
            builder = self.app_root / "backend" / "engines" / "omnivoice_build_prompt.py"
            if not python.is_file():
                raise RuntimeError("Không tìm thấy môi trường Python của OmniVoice để tạo voice.pt")
            completed = subprocess.run([str(python), str(builder), "--voice-dir", str(destination)],
                cwd=str(self.omnivoice_root), capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30 * 60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode != 0 or not (destination / "voice.pt").is_file():
                detail = completed.stderr.strip() or completed.stdout.strip() or "Không tạo được voice.pt"
                raise RuntimeError(f"Tạo hồ sơ giọng thất bại: {detail[-1200:]}")
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return next(item for item in self.list_voices() if item["id"] == destination.name)

    def voice_reference(self, voice_id: str) -> tuple[Path, dict[str, Any]]:
        voice_dir = self._voice_dir(voice_id)
        profile_path = voice_dir / "profile.json"
        if not profile_path.is_file():
            raise ValueError("Hồ sơ giọng OmniVoice chưa hoàn chỉnh")
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            audio = self._profile_file(voice_dir, profile.get("ref_audio", "ref.wav"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Hồ sơ giọng OmniVoice không hợp lệ") from exc
        if not audio.is_file():
            raise ValueError("Không tìm thấy audio tham chiếu của giọng")
        return audio, profile

    def generate(self, params: dict[str, Any]) -> dict[str, Any]:
        text = str(params.get("text", "")).strip()
        voice_id = str(params.get("voiceId", "")).strip()
        if not text:
            raise ValueError("Vui lòng nhập nội dung cần tạo giọng")
        if len(text) > self.MAX_TEXT_LENGTH:
            raise ValueError("Nội dung vượt quá 100.000 ký tự")
        voice_dir = self._voice_dir(voice_id)
        generation_id = f"studio_{time.time_ns()}_{uuid.uuid4().hex[:8]}"
        output_path = self.user_data / "outputs" / f"{generation_id}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.voice_config().get("mode") == "colab":
                generated = self.remote_generate(text, voice_id, params, output_path)
            else:
                generated = self._generate_local(text, voice_dir, params, output_path)
            if not output_path.is_file():
                raise RuntimeError("Bộ tạo giọng hoàn tất nhưng không tạo file audio")
            voices = self.list_voices()
            record = {"id": generation_id, "path": str(output_path), "name": output_path.name,
                      "bytes": output_path.stat().st_size, **generated, "format": "wav", "voiceId": voice_id,
                      "voiceName": next((v["name"] for v in voices if v["id"] == voice_id), voice_id),
                      "language": str(params.get("language", "vi")), "text": text,
                      "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if bool(params.get("createSrt")):
                srt_path = output_path.with_suffix(".srt")
                self._atomic_text(srt_path, build_srt(text, float(record.get("duration", 0))))
                record["srtPath"] = str(srt_path)
            self._prepend_history(record)
            return record
        except Exception:
            output_path.unlink(missing_ok=True)
            output_path.with_suffix(".srt").unlink(missing_ok=True)
            raise

    def history(self) -> list[dict[str, Any]]:
        with self._history_lock:
            return self._load_history_unlocked()

    def delete_history(self, generation_id: str) -> dict[str, Any]:
        with self._history_lock:
            history = self._load_history_unlocked()
            remaining = [item for item in history if str(item.get("id")) != generation_id]
            self._atomic_json(self._history_path(), remaining)
            return {"deleted": len(remaining) != len(history)}

    def _generate_local(self, text: str, voice_dir: Path, params: dict[str, Any], output_path: Path) -> dict[str, Any]:
        if not (voice_dir / "profile.json").is_file():
            raise ValueError("Giọng đã chọn chưa có hồ sơ OmniVoice hoàn chỉnh")
        python = self.omnivoice_root / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise RuntimeError("Không tìm thấy Python của OmniVoice")
        seed_value = params.get("seed")
        seed = int(seed_value) if str(seed_value or "").strip() else int(time.time_ns() % 2_147_483_647)
        started = time.perf_counter()
        self._runtime_generate({
            "text": text, "voiceDir": str(voice_dir), "output": str(output_path),
            "language": str(params.get("language", "vi")),
            "speed": float(params.get("speed", 1.0)),
            "steps": int(params.get("steps", 32)),
            "guidance": float(params.get("guidance", 2.0)),
            "seed": seed, "denoise": bool(params.get("denoise", True)),
            "postprocess": bool(params.get("postprocess", True)),
        })
        with wave.open(str(output_path), "rb") as wav:
            duration = wav.getnframes() / max(1, wav.getframerate())
        return {"duration": round(duration, 2), "generationTime": round(time.perf_counter() - started, 2), "seed": seed}

    def _runtime_generate(self, payload: dict[str, Any]) -> None:
        with self._runtime_lock:
            self._ensure_runtime_locked()
            assert self._runtime_process is not None and self._runtime_process.stdin is not None
            assert self._runtime_output is not None
            request_id = uuid.uuid4().hex
            request = {"id": request_id, "action": "generate", **payload}
            try:
                self._runtime_process.stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
                self._runtime_process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._clear_runtime_locked()
                raise RuntimeError("Runtime OmniVoice đã dừng trước khi nhận tác vụ.") from exc
            started = time.monotonic()
            last_progress = started
            stage = "model"
            logs: list[str] = []
            while True:
                try:
                    line = self._runtime_output.get(timeout=1)
                except queue.Empty:
                    line = ""
                if line is None:
                    self._clear_runtime_locked()
                    raise RuntimeError("Runtime OmniVoice đã dừng đột ngột: " + "\n".join(logs[-10:]))
                if line:
                    logs.append(line)
                    try:
                        packet = json.loads(line)
                    except ValueError:
                        packet = None
                    if not isinstance(packet, dict):
                        continue
                    if packet.get("event") == "progress" and packet.get("id") == request_id:
                        stage = str(packet.get("stage") or stage)
                        last_progress = time.monotonic()
                        self._emit_progress(stage, str(packet.get("message") or "Đang xử lý…"))
                    if packet.get("id") == request_id and "ok" in packet:
                        if packet.get("ok"):
                            return
                        raise RuntimeError(f"OmniVoice không thể tạo audio: {packet.get('error', 'Lỗi không xác định')}")
                now = time.monotonic()
                if now - started > 1800:
                    self._clear_runtime_locked(terminate=True)
                    raise RuntimeError("OmniVoice vượt quá thời gian tối đa 30 phút và đã được dừng.")
                if stage in {"model", "model_ready"} and now - last_progress > 180:
                    self._clear_runtime_locked(terminate=True)
                    raise RuntimeError("OmniVoice bị treo khi nạp model quá 180 giây và đã được dừng.")

    def _ensure_runtime_locked(self) -> None:
        if self._runtime_process and self._runtime_process.poll() is None:
            return
        python = self.omnivoice_root / ".venv" / "Scripts" / "python.exe"
        runtime = self.app_root / "backend" / "engines" / "omnivoice_runtime.py"
        child_env = os.environ.copy()
        child_env.update({"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        process = subprocess.Popen(
            [str(python), "-u", str(runtime)], cwd=str(self.omnivoice_root),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=child_env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdout is not None
        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                for line in process.stdout:
                    output.put(line.rstrip())
            finally:
                output.put(None)

        threading.Thread(target=read_output, daemon=True, name="omnivoice-runtime-output").start()
        self._runtime_process, self._runtime_output = process, output
        deadline = time.monotonic() + 60
        logs: list[str] = []
        while time.monotonic() < deadline:
            try:
                line = output.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            logs.append(line)
            try:
                packet = json.loads(line)
            except ValueError:
                continue
            if packet.get("event") == "runtime":
                self._emit_progress(str(packet.get("stage") or "startup"), str(packet.get("message") or "Đang khởi động…"))
                if packet.get("stage") == "ready":
                    return
        self._clear_runtime_locked(terminate=True)
        raise RuntimeError("Không thể khởi động runtime OmniVoice trong 60 giây: " + "\n".join(logs[-10:]))

    def unload_runtime(self) -> None:
        with self._runtime_lock:
            self._clear_runtime_locked(terminate=True)

    def _clear_runtime_locked(self, terminate: bool = False) -> None:
        process = self._runtime_process
        self._runtime_process = None
        self._runtime_output = None
        if terminate and process is not None:
            self._terminate_process_tree(process)

    def _emit_progress(self, stage: str, message: str) -> None:
        try:
            self.emit({"event": "studio.progress", "data": {"stage": stage, "message": message}})
        except Exception:
            logging.exception("Cannot emit OmniVoice studio progress")

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            process.kill()

    def _voice_dir(self, voice_id: str) -> Path:
        if not voice_id or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}", voice_id):
            raise ValueError("Mã giọng không hợp lệ")
        path = (self.voices_dir / voice_id).resolve()
        if path.parent != self.voices_dir.resolve():
            raise ValueError("Mã giọng không hợp lệ")
        return path

    @staticmethod
    def _profile_file(voice_dir: Path, value: Any) -> Path:
        candidate = (voice_dir / str(value)).resolve()
        if candidate.parent != voice_dir.resolve():
            raise ValueError("Đường dẫn trong hồ sơ giọng không hợp lệ")
        return candidate

    def _reserve_voice_dir(self, base: str) -> Path:
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        for suffix in range(1, 10_000):
            candidate = self.voices_dir / (base if suffix == 1 else f"{base}-{suffix}")
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                continue
        raise RuntimeError("Không thể cấp tên thư mục giọng duy nhất")

    def _history_path(self) -> Path:
        return self.user_data / "studio-history.json"

    def _load_history_unlocked(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._history_path().read_text(encoding="utf-8"))
            if not isinstance(data, list): return []
            return [item for item in data if isinstance(item, dict) and Path(str(item.get("path", ""))).is_file()]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return []

    def _prepend_history(self, record: dict[str, Any]) -> None:
        with self._history_lock:
            history = self._load_history_unlocked()
            self._atomic_json(self._history_path(), [record, *history][:100])

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def _atomic_json(cls, path: Path, value: Any) -> None:
        cls._atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def normalize_language(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"vi", "vietnamese", "tiếng việt"}: return "Tiếng Việt"
    if raw in {"en", "english"}: return "English"
    return str(value or "Chưa xác định")


def slugify(value: str) -> str:
    cleaned = value.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    result = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return result or f"voice-{time.time_ns()}"


def build_srt(text: str, duration: float) -> str:
    chunks = [part.strip() for part in re.split(r"(?<=[.!?…])\s+|\n+", text) if part.strip()] or [text]
    weights = [max(1, len(part)) for part in chunks]
    total, cursor, blocks = sum(weights), 0.0, []
    for index, (part, weight) in enumerate(zip(chunks, weights), 1):
        end = duration if index == len(chunks) else min(duration, cursor + duration * weight / total)
        blocks.append(f"{index}\n{format_srt_time(cursor)} --> {format_srt_time(end)}\n{part}")
        cursor = end
    return "\n\n".join(blocks) + "\n"


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
