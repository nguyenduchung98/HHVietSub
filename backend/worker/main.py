from __future__ import annotations

import argparse
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import wave
import zipfile
import urllib.error
import urllib.request
import mimetypes
import os
import queue
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.settings_service import SettingsService
from backend.services.model_service import ModelService
from backend.services.tts_api_service import TtsApiService
from backend.services.srt_job_service import SrtJobService
from backend.services.subtitle_service import SubtitleService
from backend.services.gemini_translation_service import GeminiTranslationService
from backend.services.voice_studio_service import VoiceStudioService
from backend.rpc.errors import rpc_error


def resolve_runtime_path(env_name: str, *candidates: Path) -> Path:
    """Resolve an optional external component without tying it to one PC."""
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


APP_ROOT = resolve_runtime_path("HHVIETSUB_APP_ROOT", ROOT)
LEGACY_OMNIVOICE = resolve_runtime_path(
    "HHVIETSUB_OMNIVOICE_ROOT",
    APP_ROOT / "runtime" / "OmniVoice",
    Path.home() / "OmniVoice",
    Path(r"D:\OmniVoice"),
)
VIENEU_RUNTIME = resolve_runtime_path(
    "HHVIETSUB_VIENEU_ROOT",
    APP_ROOT / "runtime" / "VieNeu-TTS",
)
LEGACY_CAPCUT = resolve_runtime_path(
    "HHVIETSUB_CAPCUT_BRIDGE_ROOT",
    APP_ROOT / "runtime" / "Dich_CapCut_v2",
    Path.home() / "Dich_CapCut_v2",
    Path(r"D:\Dịch-Đồng Bộ\Dich_CapCut_v2"),
)

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Worker:
    def __init__(self, user_data: Path):
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsService(self.user_data)
        self.models = ModelService(APP_ROOT, emit)
        self.tts_api = TtsApiService(self.settings)
        self.srt_jobs = SrtJobService(self.user_data, emit)
        self.ffmpeg_sync_lock = threading.Lock()
        self.gemini_translation = GeminiTranslationService(LEGACY_CAPCUT)
        self.voice_studio = VoiceStudioService(
            self.user_data, APP_ROOT, LEGACY_OMNIVOICE, self._voice_config, self._remote_generate, emit
        )
        self.routes: dict[str, Callable[[dict[str, Any]], Any]] = {
            "system.ping": self.ping,
            "system.info": self.system_info,
            "voice.list": self.voice_list,
            "voice.languages": self.voice_languages,
            "voice.create": self.voice_create,
            "project.list": self.project_list,
            "settings.get": self.settings_get,
            "settings.voice.save": self.voice_settings_save,
            "settings.voice.test": self.voice_settings_test,
            "settings.tts.get": self.tts_settings_get,
            "settings.tts.save": self.tts_settings_save,
            "settings.tts.test": self.tts_settings_test,
            "settings.secrets.export": self.secrets_export,
            "settings.secrets.set": self.secrets_set,
            "models.list": self.models_list,
            "models.download": self.models_download,
            "models.delete": self.models_delete,
            "tts.voices.list": self.tts_voices_list,
            "tts.voice.preview": self.tts_voice_preview,
            "subtitle.parse": self.subtitle_parse,
            "subtitle.save": self.subtitle_save,
            "subtitle.translate": self.subtitle_translate,
            "subtitle.translate.browser": self.subtitle_translate_browser,
            "gemini.open": self.gemini_open,
            "gemini.login": self.gemini_login,
            "studio.generate": self.studio_generate,
            "studio.history": self.studio_history,
            "studio.history.delete": self.studio_history_delete,
            "srt.voice.generate": self.srt_voice_generate,
            "srt.voice.regenerate": self.srt_voice_generate,
            "srt.voice.control": self.srt_voice_control,
            "srt.voice.latest": self.srt_voice_latest,
            "srt.voice.list": self.srt_voice_list,
            "srt.voice.get": self.srt_voice_get,
            "capcut.project.validate": self.capcut_project_validate,
            "capcut.project.validate_existing": self.capcut_project_validate_existing,
            "capcut.project.create": self.capcut_project_create,
            "capcut.project.sync": self.capcut_project_sync,
            "capcut.open": self.capcut_open,
            "ffmpeg.sync.validate": self.ffmpeg_sync_validate,
            "ffmpeg.sync.create": self.ffmpeg_sync_create,
        }

    def ping(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"online": True, "version": "0.1.0-dev", "protocol": 1}

    def system_info(self, _params: dict[str, Any]) -> dict[str, Any]:
        components = {
            "omnivoice": LEGACY_OMNIVOICE,
            "vieneu": VIENEU_RUNTIME,
            "capcutBridge": LEGACY_CAPCUT,
        }
        return {
            "python": sys.version.split()[0],
            "user_data": str(self.user_data),
            "project_root": str(APP_ROOT),
            "components": {
                name: {"path": str(component), "available": component.is_dir()}
                for name, component in components.items()
            },
        }

    def voice_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.voice_studio.list_voices()
        voices_dir = LEGACY_OMNIVOICE / "voices"
        voices: list[dict[str, Any]] = []
        if not voices_dir.exists():
            return voices
        for profile_path in sorted(voices_dir.glob("*/profile.json")):
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                audio = profile_path.parent / str(profile.get("ref_audio", ""))
                prompt = profile_path.parent / str(profile.get("voice_prompt", "voice.pt"))
                voices.append({
                    "id": profile_path.parent.name,
                    "name": str(profile.get("name") or profile_path.parent.name),
                    "language": normalize_language(profile.get("language")),
                    # Local OmniVoice can clone directly from reference audio on
                    # the first run; voice.pt is only a precomputed optimization.
                    "ready": audio.is_file(),
                    "promptReady": prompt.is_file(),
                    "source": "OmniVoice",
                    "referenceAudio": str(audio) if audio.exists() else None,
                })
            except (OSError, ValueError, TypeError) as exc:
                logging.warning("Invalid voice profile %s: %s", profile_path, exc)
        for audio in sorted(voices_dir.iterdir()):
            if audio.is_file() and audio.suffix.lower() in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
                voices.append({"id": audio.stem.lower().replace(" ", "-"), "name": audio.stem, "language": "Chưa xác định", "ready": False, "source": "Legacy audio", "referenceAudio": str(audio)})
        return voices

    def voice_languages(self, _params: dict[str, Any]) -> list[dict[str, str]]:
        return self.voice_studio.languages()
        """Return the complete language catalog shipped with OmniVoice."""
        languages_path = LEGACY_OMNIVOICE / "docs" / "languages.md"
        languages: list[dict[str, str]] = [{"id": "auto", "name": "Tự động nhận diện"}]
        try:
            content = languages_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                match = re.match(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
                if not match:
                    continue
                name, language_id = match.group(1).strip(), match.group(2).strip()
                if language_id and language_id not in {item["id"] for item in languages}:
                    languages.append({"id": language_id, "name": name})
        except OSError as exc:
            logging.warning("Cannot read OmniVoice language catalog: %s", exc)
        if len(languages) == 1:
            languages.extend([
                {"id": "vi", "name": "Vietnamese"}, {"id": "en", "name": "English"},
                {"id": "zh", "name": "Chinese"}, {"id": "ja", "name": "Japanese"},
                {"id": "ko", "name": "Korean"}, {"id": "es", "name": "Spanish"},
                {"id": "fr", "name": "French"}, {"id": "de", "name": "German"},
            ])
        return languages

    def project_list(self, _params: dict[str, Any]) -> list[dict[str, str]]:
        config_path = LEGACY_CAPCUT / "config.json"
        if not config_path.exists():
            return []
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            root = Path(str(config.get("capcut_path", "")))
        except (OSError, ValueError, TypeError):
            return []
        if not root.is_dir():
            return []
        result: list[dict[str, str]] = []
        for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if child.is_dir():
                result.append({"name": child.name, "folder": child.name, "path": str(child)})
        return result[:100]

    def voice_create(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.voice_studio.create_voice(params)
        name = str(params.get("name", "")).strip()
        audio_path = Path(str(params.get("audioPath", ""))).resolve()
        language = str(params.get("language", "auto")).strip() or "auto"
        ref_text = str(params.get("refText", "")).strip()
        notes = str(params.get("notes", "")).strip()
        if not name:
            raise ValueError("Vui lòng nhập tên giọng")
        if not bool(params.get("consentConfirmed")):
            raise ValueError("Bạn cần xác nhận quyền sử dụng giọng nói")
        allowed = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm"}
        if not audio_path.is_file() or audio_path.suffix.lower() not in allowed:
            raise ValueError("Audio tham chiếu không hợp lệ")
        if audio_path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Audio tham chiếu vượt quá 50 MB")
        voice_id = slugify(name)
        voices_dir = LEGACY_OMNIVOICE / "voices"
        destination = voices_dir / voice_id
        suffix = 2
        while destination.exists():
            destination = voices_dir / f"{voice_id}-{suffix}"
            suffix += 1
        destination.mkdir(parents=True)
        ref_name = f"ref{audio_path.suffix.lower()}"
        try:
            shutil.copy2(audio_path, destination / ref_name)
            (destination / "ref_text.txt").write_text(ref_text, encoding="utf-8")
            profile = {
                "name": name, "language": language, "ref_audio": ref_name,
                "ref_text_file": "ref_text.txt", "voice_prompt": "voice.pt",
                "model": "k2-fsa/OmniVoice", "device": "auto",
                "preprocess_prompt": False, "auto_transcribe": not bool(ref_text),
                "notes": notes, "consent_confirmed": True,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            (destination / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            python = LEGACY_OMNIVOICE / ".venv" / "Scripts" / "python.exe"
            builder = ROOT / "backend" / "engines" / "omnivoice_build_prompt.py"
            if not python.is_file():
                raise RuntimeError("Không tìm thấy môi trường Python của OmniVoice để tạo voice.pt")
            completed = subprocess.run(
                [str(python), str(builder), "--voice-dir", str(destination)],
                cwd=str(LEGACY_OMNIVOICE), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30 * 60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0 or not (destination / "voice.pt").is_file():
                detail = completed.stderr.strip() or completed.stdout.strip() or "Không tạo được voice.pt"
                raise RuntimeError(f"Tạo hồ sơ giọng thất bại: {detail[-1200:]}")
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return next(item for item in self.voice_list({}) if item["id"] == destination.name)

    def settings_get(self, _params: dict[str, Any]) -> dict[str, Any]:
        config_path = LEGACY_CAPCUT / "config.json"
        old = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        profile_value = Path(str(old.get("chrome_profile", "../chrome_profile")))
        profile_path = profile_value if profile_value.is_absolute() else (LEGACY_CAPCUT / profile_value).resolve()
        voice_config = self._voice_config()
        voice_config["token"] = ""
        return {"omnivoiceRoot": str(LEGACY_OMNIVOICE), "legacyCapCutRoot": str(LEGACY_CAPCUT), "ttsEngine": "omnivoice", "voiceBackend": voice_config,
                "gemini": {"url": old.get("endpoint", ""), "saved": old.get("gem_links", []),
                            "selected": old.get("selected_gem_name", ""), "models": old.get("model_values", []),
                            "model": old.get("model", "3.1 Pro"), "batch": int(old.get("batch", 200)),
                            "workers": int(old.get("workers", 1)), "profileReady": profile_path.is_dir(),
                            "profilePath": str(profile_path)}}

    def _voice_config(self) -> dict[str, Any]:
        return self.settings.voice_config()

    def voice_settings_save(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.settings.save_voice(params)

    def _get_hf_hub_dir(self, repo_id: str) -> Path:
        return self.models.hub_dir(repo_id)

    def _is_model_downloaded(self, repo_id: str) -> bool:
        return self.models.is_downloaded(repo_id)

    def models_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.models.list_models()
    def models_download(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.models.download(str(params.get("modelId", "")).strip())
    def models_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.models.delete(str(params.get("modelId", "")).strip())
    def _remote_request(self, route: str, fields: dict[str, Any] | None = None,
                        files: dict[str, Path] | None = None, timeout: int = 1800) -> tuple[bytes, Any]:
        config = self._voice_config()
        if not config["url"]:
            raise RuntimeError("Chưa cấu hình URL Google Colab")
        headers = {"User-Agent": "HHVietSub/0.1"}
        if config["token"]:
            headers["Authorization"] = f"Bearer {config['token']}"
        data = None
        if fields is not None or files:
            boundary = f"----HHVietSub{uuid.uuid4().hex}"
            body = bytearray()
            for key, value in (fields or {}).items():
                body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
            for key, path in (files or {}).items():
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"))
                body.extend(path.read_bytes()); body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode("ascii"))
            data = bytes(body); headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = urllib.request.Request(config["url"] + route, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
            return response.read(), response.headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Colab API ({exc.code}): {detail[:800]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Mất kết nối Google Colab: {exc.reason}") from exc

    def voice_settings_test(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            self.voice_settings_save(params)
        raw, _ = self._remote_request("/health", timeout=30)
        result = json.loads(raw.decode("utf-8"))
        runtime = result.get("runtime", {})
        return {"ok": bool(result.get("ok")), "device": runtime.get("device") or "gpu",
                "status": runtime.get("status") or "unknown", "detail": runtime.get("detail") or ""}

    def secrets_export(self, _params: dict[str, Any]) -> dict[str, str]:
        """Internal migration endpoint; Electron blocks renderer access."""
        return self.settings.export_secrets()

    def secrets_set(self, params: dict[str, Any]) -> dict[str, Any]:
        """Load decrypted secrets into memory and scrub legacy plaintext files."""
        return self.settings.set_secrets(params)

    @staticmethod
    def _parse_keys(raw: str) -> list[str]:
        return SettingsService.parse_keys(raw)

    def _tts_api_keys(self, provider: str) -> list[str]:
        return self.settings.tts_keys(provider)

    def tts_settings_get(self, _params: dict[str, Any]) -> dict[str, Any]:
        return self.settings.tts_status()

    def tts_settings_save(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.settings.save_tts(params)

    def tts_settings_test(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.tts_api.test_keys(str(params.get("provider", "")), str(params.get("key", "")).strip())
    def tts_voices_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.tts_api.list_voices(str(params.get("engine", "")), str(params.get("provider", "minimax")), str(params.get("language", "auto")))
    def tts_voice_preview(self, params: dict[str, Any]) -> dict[str, str]:
        return self.tts_api.preview(str(params.get("engine", "")), str(params.get("url", "")).strip())
    def _api_generate_one(self, engine: str, entry: dict[str, Any], params: dict[str, Any], output: Path, control: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.tts_api.generate_one(engine, entry, params, output, control)
    def _srt_job_path(self, job_id: str) -> Path:
        return self.srt_jobs.path(job_id)

    def _save_srt_job(self, job: dict[str, Any]) -> None:
        self.srt_jobs.save(job)

    def srt_voice_latest(self, _params: dict[str, Any]) -> dict[str, Any] | None:
        return self.srt_jobs.latest()

    def srt_voice_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.srt_jobs.list_jobs()

    def srt_voice_get(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.srt_jobs.get(str(params.get("jobId", "")))

    def srt_voice_control(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.srt_jobs.control(str(params.get("jobId", "")), str(params.get("action", "")))

    def _srt_api_generate(self, engine: str, params: dict[str, Any], entries: list[Any]) -> dict[str, Any]:
        output_dir = Path(str(params.get("outputDir", ""))).resolve(); output_dir.mkdir(parents=True, exist_ok=True)
        requested_workers = max(1, int(params.get("apiWorkers", 3)))
        workers = min(32, requested_workers)
        request_interval = max(0.0, min(60.0, float(params.get("apiRequestInterval", 10))))
        request_gate = {"default": threading.Lock(), "direct": threading.Lock(), "space": threading.Lock()}
        next_request_at = {"default": 0.0, "direct": 0.0, "space": 0.0}
        items = []; pending: list[tuple[dict[str, Any], Path]] = []
        job_id = str(params.get("jobId") or f"srt-{int(time.time()*1000)}")
        control = self.srt_jobs.register(job_id)
        for position, raw in enumerate(entries, 1):
            if not isinstance(raw, dict) or not str(raw.get("text", "")).strip(): continue
            entry = {**raw, "id": int(raw.get("id", position)), "text": str(raw["text"]).strip()}
            output = output_dir / f"{entry['id']:04d}.{'mp3' if engine == 'capcut' else 'wav'}"
            if bool(params.get("skipExisting", True)) and output.is_file():
                if engine == "capcut":
                    duration = 0
                else:
                    with wave.open(str(output), "rb") as wav:
                        duration = wav.getnframes() / max(1, wav.getframerate())
                items.append({**entry, "status": "completed", "file": str(output), "duration": round(duration, 2), "skipped": True})
            else: pending.append((entry, output))

        def wait_for_api_slot(entry: dict[str, Any]) -> bool:
            """Space API starts apart while allowing in-flight work to overlap."""
            lane = "default"
            if engine == "capcut" and str(params.get("capcutBackend", "")).lower() == "hybrid":
                lane = "direct" if int(entry.get("id", 1)) % 2 else "space"
            with request_gate[lane]:
                while True:
                    while control["pause"].is_set() and not control["cancel"].is_set():
                        time.sleep(.2)
                    if control["cancel"].is_set():
                        return False
                    remaining = next_request_at[lane] - time.monotonic()
                    if remaining <= 0:
                        next_request_at[lane] = time.monotonic() + request_interval
                        emit({"event": "srt.voice.progress", "data": {
                            "event": "api-start", "id": entry["id"],
                            "requestInterval": request_interval,
                        }})
                        return True
                    time.sleep(min(.2, remaining))

        def generate_one(job: tuple[dict[str, Any], Path]) -> dict[str, Any]:
            entry, output = job; last_error = None
            while control["pause"].is_set() and not control["cancel"].is_set(): time.sleep(.2)
            if control["cancel"].is_set(): return {**entry, "status": "pending", "error": "Đã huỷ trước khi gửi", "engine": engine}
            for attempt in range(1, 4):
                if control["cancel"].is_set(): return {**entry, "status": "pending", "error": "Đã huỷ tác vụ", "engine": engine}
                emit({"event": "srt.voice.progress", "data": {"event": "attempt", "id": entry["id"], "attempt": attempt}})
                if not wait_for_api_slot(entry):
                    return {**entry, "status": "pending", "error": "Đã huỷ trước khi gửi API", "engine": engine}
                try: return self._api_generate_one(engine, entry, params, output, control)
                except Exception as exc:
                    last_error = exc
                    err_msg = str(exc).lower()
                    if "đã huỷ" in err_msg or control["cancel"].is_set():
                        return {**entry, "status": "pending", "error": "Đã huỷ tác vụ", "engine": engine}
                    is_rate_limit = "429" in err_msg or "rate_limit" in err_msg or "rate limited" in err_msg or "too many requests" in err_msg
                    if attempt < 3:
                        if is_rate_limit:
                            wait_seconds = attempt * 4
                            emit({"event": "srt.voice.progress", "data": {"event": "warning", "message": f"API (429 Rate Limit) ở câu {entry['id']}. Đang tạm hoãn {wait_seconds}s trước khi thử lại..."}})
                            for _ in range(int(wait_seconds / 0.2)):
                                if control["cancel"].is_set(): return {**entry, "status": "pending", "error": "Đã huỷ trong khi chờ rate limit", "engine": engine}
                                time.sleep(0.2)
                        else:
                            for _ in range(int(attempt / 0.1)):
                                while control["pause"].is_set() and not control["cancel"].is_set(): time.sleep(.2)
                                if control["cancel"].is_set(): return {**entry, "status": "pending", "error": "Đã huỷ trước khi thử lại", "engine": engine}
                                time.sleep(0.1)
            return {**entry, "status": "failed", "error": str(last_error), "engine": engine}

        total = len(items) + len(pending); done = len(items)
        job_state = {"jobId": job_id, "state": "running", "engine": engine, "provider": params.get("apiProvider"), "model": params.get("apiModel"), "voiceId": params.get("apiVoiceId"), "subtitleLanguage": params.get("subtitleLanguage", "auto"), "workers": workers, "apiRequestInterval": request_interval, "outputDir": str(output_dir), "entries": entries, "items": list(items), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self._save_srt_job(job_state); emit({"event": "srt.voice.job", "data": {"jobId": job_id, "state": "running"}})
        for item in items: emit({"event": "srt.voice.progress", "data": {"event": "progress", "done": done, "total": total, "item": item, "workers": workers}})
        with ThreadPoolExecutor(max_workers=min(workers, max(1, len(pending)))) as executor:
            futures = [executor.submit(generate_one, job) for job in pending]
            for future in as_completed(futures):
                item = future.result(); items.append(item); done += 1
                job_state["items"] = sorted(items, key=lambda x: int(x.get("id", 0))); job_state["state"] = "cancelled" if control["cancel"].is_set() else ("paused" if control["pause"].is_set() else "running"); self._save_srt_job(job_state)
                emit({"event": "srt.voice.progress", "data": {"event": "progress", "done": done, "total": total, "item": item, "workers": workers}})
        items.sort(key=lambda item: int(item.get("id", 0)))
        final_state = "cancelled" if control["cancel"].is_set() else "completed"
        job_state.update({"state": final_state, "items": items, "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}); self._save_srt_job(job_state)
        self.srt_jobs.remove(job_id)
        manifest = output_dir / "manifest.json"; manifest.write_text(json.dumps({"jobId": job_id, "state": final_state, "engine": engine, "workers": workers, "apiRequestInterval": request_interval, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = sum(x.get("status") == "completed" for x in items)
        return {"jobId": job_id, "state": final_state, "outputDir": str(output_dir), "manifestPath": str(manifest), "items": items, "completed": completed, "failed": sum(x.get("status") == "failed" for x in items), "total": len(items)}

    def _launch_chrome(self, url: str) -> dict[str, Any]:
        settings = self.settings_get({})["gemini"]
        candidates = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                      Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                      Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"]
        chrome = next((path for path in candidates if path.is_file()), None)
        if not chrome:
            raise RuntimeError("Không tìm thấy Google Chrome")
        subprocess.Popen([str(chrome), f"--user-data-dir={settings['profilePath']}", "--profile-directory=Default", url],
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        return {"opened": True, "url": url}

    def gemini_open(self, params: dict[str, Any]) -> dict[str, Any]:
        url = str(params.get("url") or self.settings_get({})["gemini"]["url"])
        if not url.startswith("https://gemini.google.com/"):
            raise ValueError("Link Gem không hợp lệ")
        return self._launch_chrome(url)

    def gemini_login(self, _params: dict[str, Any]) -> dict[str, Any]:
        return self._launch_chrome("https://accounts.google.com/")

    def subtitle_parse(self, params: dict[str, Any]) -> dict[str, Any]:
        return SubtitleService.parse(Path(str(params.get("path", ""))))
    def subtitle_save(self, params: dict[str, Any]) -> dict[str, Any]:
        return SubtitleService.save(
            Path(str(params.get("sourcePath", ""))), params.get("entries"), str(params.get("outputPath", ""))
        )
    def subtitle_translate(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.gemini_translation.translate_api(params)
    def subtitle_translate_browser(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.gemini_translation.translate_browser(params)
    def capcut_project_validate(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.capcut_project_v1 import validate_inputs
        return validate_inputs(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
                               Path(str(params.get("voiceDir", ""))))

    def capcut_project_validate_existing(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.capcut_project_v1 import validate_existing_inputs
        return validate_existing_inputs(Path(str(params.get("projectPath", ""))),
                                        Path(str(params.get("srtPath", ""))),
                                        Path(str(params.get("voiceDir", ""))))

    def capcut_open(self, _params: dict[str, Any]) -> dict[str, Any]:
        executable = Path.home() / "AppData" / "Local" / "CapCut" / "Apps" / "CapCut.exe"
        if not executable.is_file():
            raise RuntimeError("Không tìm thấy CapCut.exe")
        subprocess.Popen([str(executable)], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        return {"opened": True}

    def capcut_project_create(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.capcut_project_v1 import create_project
        def logger(message: str) -> None:
            emit({"event": "capcut.project.progress", "data": {"message": message}})
        return create_project(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
                              Path(str(params.get("voiceDir", ""))), str(params.get("projectName", "")), logger)

    def capcut_project_sync(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.capcut_project_v1 import sync_existing_project
        def logger(message: str) -> None:
            emit({"event": "capcut.project.progress", "data": {"message": message}})
        return sync_existing_project(Path(str(params.get("projectPath", ""))),
                                     Path(str(params.get("srtPath", ""))),
                                     Path(str(params.get("voiceDir", ""))), logger)

    def ffmpeg_sync_validate(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.ffmpeg_sync_v1 import validate_inputs
        voice_speed = float(params.get("voiceSpeed", 1.0))
        return validate_inputs(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
                               Path(str(params.get("voiceDir", "")).strip()), voice_speed=voice_speed)

    def ffmpeg_sync_create(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.ffmpeg_sync_v1 import render
        if not self.ffmpeg_sync_lock.acquire(blocking=False):
            raise RuntimeError("Một job FFmpeg đang chạy. Hãy chờ job hiện tại hoàn tất hoặc khởi động lại ứng dụng nếu job đã bị gián đoạn.")
        def logger(message: str) -> None:
            emit({"event": "ffmpeg.sync.progress", "data": {"message": message}})
        try:
            output_dir = Path(str(params.get("outputDir", ""))).resolve()
            if not output_dir.is_dir():
                raise ValueError("Hãy chọn thư mục lưu kết quả")
            encoder = str(params.get("encoder", "auto"))
            voice_speed = float(params.get("voiceSpeed", 1.0))
            change_pitch = bool(params.get("changePitch", False))
            video_volume_db = float(params.get("videoVolumeDb", -20.0))
            merge_audio = bool(params.get("mergeAudio", True))
            return render(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
                          Path(str(params.get("voiceDir", ""))), output_dir,
                          str(params.get("projectName", "")), logger,
                          int(params.get("chunkPieces", 100)), encoder_choice=encoder,
                          voice_speed=voice_speed, change_pitch=change_pitch,
                          video_volume_db=video_volume_db, merge_audio=merge_audio)
        finally:
            self.ffmpeg_sync_lock.release()

    def _voice_reference(self, voice_id: str) -> tuple[Path, dict[str, Any]]:
        return self.voice_studio.voice_reference(voice_id)
        voice_dir = LEGACY_OMNIVOICE / "voices" / voice_id
        profile_path = voice_dir / "profile.json"
        if not profile_path.is_file(): raise ValueError("Hồ sơ giọng OmniVoice chưa hoàn chỉnh")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        audio = voice_dir / str(profile.get("ref_audio", "ref.wav"))
        if not audio.is_file(): raise ValueError("Không tìm thấy audio tham chiếu của giọng")
        return audio, profile

    def _remote_generate(self, text: str, voice_id: str, params: dict[str, Any], output: Path) -> dict[str, Any]:
        audio, profile = self._voice_reference(voice_id)
        seed_value = params.get("seed")
        seed = int(seed_value) if str(seed_value or "").strip() else int(time.time_ns() % 2_147_483_647)
        fields = {"text": text, "ref_text": str(profile.get("ref_text", "")), "language": str(params.get("language", "vi")),
                  "speed": float(params.get("speed", 1.0)), "num_step": int(params.get("steps", 32)),
                  "guidance_scale": float(params.get("guidance", 2.0)), "seed": seed,
                  "denoise": str(bool(params.get("denoise", False))).lower(),
                  "postprocess_output": str(bool(params.get("postprocess", True))).lower(), "output_format": "wav"}
        started = time.perf_counter(); raw, headers = self._remote_request("/generate", fields, {"ref_audio": audio})
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(raw)
        with wave.open(str(output), "rb") as wav: duration = wav.getnframes() / max(1, wav.getframerate())
        return {"duration": round(duration, 2), "generationTime": round(time.perf_counter() - started, 2),
                "seed": int(headers.get("X-Seed", seed))}

    def _remote_generate_batch(self, entries: list[dict[str, Any]], voice_id: str,
                               params: dict[str, Any], output_dir: Path) -> list[dict[str, Any]]:
        voice_dir = LEGACY_OMNIVOICE / "voices" / voice_id
        profile = json.loads((voice_dir / "profile.json").read_text(encoding="utf-8"))
        prompt_path = voice_dir / str(profile.get("voice_prompt", "voice.pt"))
        if not prompt_path.is_file():
            raise FileNotFoundError("Hồ sơ giọng chưa có voice.pt để tạo batch nhanh trên Colab")
        fields = {
            "entries": json.dumps(entries, ensure_ascii=False),
            "language": str(params.get("language", "vi")), "speed": float(params.get("speed", 1.0)),
            "num_step": int(params.get("steps", 32)), "guidance_scale": float(params.get("guidance", 2.0)),
            "denoise": str(bool(params.get("denoise", False))).lower(),
            "postprocess_output": str(bool(params.get("postprocess", True))).lower(),
        }
        if str(params.get("seed") or "").strip():
            fields["seed"] = int(params["seed"])
        raw, _ = self._remote_request("/generate-batch", fields, {"voice_prompt": prompt_path}, timeout=30 * 60)
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            names = set(bundle.namelist())
            if "manifest.json" not in names:
                raise RuntimeError("Colab không trả về manifest batch")
            manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
            items = manifest.get("items", []) if isinstance(manifest, dict) else []
            output_dir.mkdir(parents=True, exist_ok=True)
            for item in items:
                if not isinstance(item, dict) or item.get("status") != "completed":
                    continue
                filename = f"{int(item['id']):04d}.wav"
                if filename not in names:
                    item.update(status="failed", error="Batch thiếu file WAV")
                    continue
                destination = output_dir / filename
                destination.write_bytes(bundle.read(filename))
                item["file"] = str(destination)
        return items

    def srt_voice_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        entries = params.get("entries")
        engine = str(params.get("engine", "omnivoice")).lower()
        voice_id = str(params.get("voiceId", "")).strip()
        if not isinstance(entries, list) or not entries:
            raise ValueError("Không có câu phụ đề để tạo giọng")
        if engine in {"ai33", "aimax", "capcut"}:
            job_params = {**params, "jobId": str(params.get("jobId") or f"srt-{int(time.time() * 1000)}")}
            try:
                return self._srt_api_generate(engine, job_params, entries)
            finally:
                self.srt_jobs.remove(job_params["jobId"])
        if engine == "vieneu":
            job_params = {**params, "jobId": str(params.get("jobId") or f"srt-{int(time.time() * 1000)}")}
            try:
                return self._srt_vieneu_generate(job_params, entries)
            finally:
                self.srt_jobs.remove(job_params["jobId"])
        if engine != "omnivoice":
            raise ValueError("Mô hình tạo giọng không hợp lệ")
        # The Studio runtime keeps OmniVoice resident in VRAM. Release it before
        # starting the dedicated SRT batch worker so the model is never loaded twice.
        self.voice_studio.unload_runtime()
        if self._voice_config()["mode"] == "local" and not self._is_model_downloaded("k2-fsa/OmniVoice"):
            raise RuntimeError("Chưa tải Model OmniVoice cục bộ! Vui lòng vào Cấu hình ⚙️ ➔ Tải Model để bắt đầu tạo giọng.")
        # Tạo từ SRT dùng OmniVoice cục bộ; Colab không được chọn ngầm từ cấu hình chung.
        if False and self._voice_config()["mode"] == "colab":
            voice_id = str(params.get("voiceId", "")).strip()
            output_value = str(params.get("outputDir", "")).strip()
            output_dir = Path(output_value).resolve() if output_value else self.user_data / "srt-voice-output"
            output_dir.mkdir(parents=True, exist_ok=True); items = []; pending = []
            for position, entry in enumerate(entries, 1):
                if not isinstance(entry, dict) or not str(entry.get("text", "")).strip(): continue
                item_id = int(entry.get("id", position)); output = output_dir / f"{item_id:04d}.wav"
                normalized = {**entry, "id": item_id, "text": str(entry["text"]).strip()}
                if bool(params.get("skipExisting", True)) and output.is_file():
                    with wave.open(str(output), "rb") as wav: duration = wav.getnframes() / max(1, wav.getframerate())
                    items.append({**normalized, "status": "completed", "file": str(output),
                                  "duration": round(duration, 2), "skipped": True})
                else:
                    pending.append(normalized)
            if pending:
                # Cloudflare quick tunnels return 524 when one HTTP request runs for ~100 seconds.
                # Five subtitles keeps each inference request safely below that limit on a T4.
                remote_chunk_size = 5
                for offset in range(0, len(pending), remote_chunk_size):
                    chunk = pending[offset:offset + remote_chunk_size]
                    emit({"event": "srt.voice.progress", "data": {"done": len(items), "total": len(entries),
                                                                      "current": chunk[0]["id"], "batch": True,
                                                                      "batchSize": len(chunk)}})
                    generated = None
                    last_error = None
                    for request_attempt in range(1, 4):
                        try:
                            generated = self._remote_generate_batch(chunk, voice_id, params, output_dir)
                            break
                        except Exception as exc:
                            last_error = exc
                            emit({"event": "srt.voice.progress", "data": {"done": len(items), "total": len(entries),
                                                                              "current": chunk[0]["id"], "batch": True,
                                                                              "requestAttempt": request_attempt}})
                            if request_attempt < 3:
                                time.sleep(2 * request_attempt)
                    if generated is None:
                        raise RuntimeError(f"Colab batch {chunk[0]['id']}-{chunk[-1]['id']} thất bại: {last_error}")
                    completed_before = len(items)
                    items.extend(generated)
                    for index, item in enumerate(generated, 1):
                        emit({"event": "srt.voice.progress", "data": {"done": completed_before + index, "total": len(entries),
                                                                          "item": item, "batch": True}})
            items.sort(key=lambda item: int(item.get("id", 0)))
            manifest_path = output_dir / "manifest.json"
            manifest_path.write_text(json.dumps({"voiceId": voice_id, "outputDir": str(output_dir), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
            completed = sum(item["status"] == "completed" for item in items)
            return {"outputDir": str(output_dir), "manifestPath": str(manifest_path), "items": items,
                    "completed": completed, "failed": len(items) - completed, "total": len(items)}
        voice_dir = LEGACY_OMNIVOICE / "voices" / voice_id
        if not (voice_dir / "profile.json").is_file():
            raise ValueError("Hồ sơ giọng OmniVoice chưa hoàn chỉnh")
        python = LEGACY_OMNIVOICE / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise RuntimeError("Không tìm thấy môi trường Python của D:\\OmniVoice")
        output_value = str(params.get("outputDir", "")).strip()
        output_dir = Path(output_value).resolve() if output_value else self.user_data / "srt-voice-output"
        output_dir.mkdir(parents=True, exist_ok=True)
        clean_entries = []
        for position, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text", "")).strip()
            if not text:
                continue
            clean_entries.append({
                "id": int(entry.get("id", position)), "start": str(entry.get("start", "")),
                "end": str(entry.get("end", "")), "text": text,
            })
        if not clean_entries:
            raise ValueError("Không có câu phụ đề hợp lệ để tạo giọng")
        job_dir = self.user_data / "jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        job_path = job_dir / f"srt_voice_{int(time.time() * 1000)}.json"
        job = {
            "voiceDir": str(voice_dir), "outputDir": str(output_dir), "entries": clean_entries,
            "modelPath": str(self.models.snapshot_path("k2-fsa/OmniVoice")),
            "language": str(params.get("language", "vi")), "speed": float(params.get("speed", 1.0)),
            "steps": int(params.get("steps", 32)), "guidance": float(params.get("guidance", 2.0)),
            "seed": params.get("seed"), "denoise": bool(params.get("denoise", False)),
            "postprocess": bool(params.get("postprocess", True)),
            "skipExisting": bool(params.get("skipExisting", True)),
            "batchSize": max(1, min(16, int(params.get("omniBatchSize", 4)))),
        }
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        job_id = str(params.get("jobId") or f"srt-{int(time.time() * 1000)}")
        control = self.srt_jobs.register(job_id)
        job_state = {
            "jobId": job_id, "state": "running", "engine": "omnivoice", "provider": "local",
            "model": "k2-fsa/OmniVoice", "voiceId": voice_id,
            "subtitleLanguage": job["language"], "workers": 1, "outputDir": str(output_dir),
            "entries": clean_entries, "items": [], "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._save_srt_job(job_state)
        emit({"event": "srt.voice.job", "data": {"jobId": job_id, "state": "running"}})
        helper = ROOT / "backend" / "engines" / "omnivoice_srt_batch.py"
        command = [str(python), "-u", str(helper), "--job", str(job_path)]
        child_env = os.environ.copy()
        child_env.update({"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        process = subprocess.Popen(command, cwd=str(LEGACY_OMNIVOICE), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                   stdin=subprocess.DEVNULL, bufsize=1, env=child_env)
        manifest_path = output_dir / "manifest.json"
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            previous_items = previous_manifest.get("items", []) if isinstance(previous_manifest, dict) else []
        except (OSError, ValueError, TypeError):
            previous_items = []
        manifest = {"voiceId": voice_id, "outputDir": str(output_dir), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": []}
        by_id: dict[int, dict[str, Any]] = {int(item["id"]): item for item in previous_items if isinstance(item, dict) and "id" in item}
        requested_ids = {int(entry["id"]) for entry in clean_entries}
        child_error = ""
        cancelled = False
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_child_output() -> None:
            try:
                for child_line in process.stdout:
                    output_queue.put(child_line)
            finally:
                output_queue.put(None)

        threading.Thread(target=read_child_output, daemon=True).start()
        last_output_at = time.monotonic()
        received_startup = False
        while True:
            timeout_seconds = 45 if not received_startup else 180
            try:
                line = output_queue.get(timeout=1.0)
            except queue.Empty:
                if control["cancel"].is_set():
                    cancelled = True
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    break
                if process.poll() is not None:
                    break
                if time.monotonic() - last_output_at <= timeout_seconds:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                phase = "khởi động Python" if not received_startup else "nạp model hoặc tạo câu"
                job_state.update({"state": "failed", "error": f"Timeout khi {phase}"})
                self._save_srt_job(job_state)
                self.srt_jobs.remove(job_id)
                raise RuntimeError(
                    f"OmniVoice bị treo khi {phase} quá {timeout_seconds} giây. "
                    "Tiến trình đã được dừng an toàn; hãy thử lại sau khi đóng tác vụ GPU khác."
                )
            if line is None:
                break
            last_output_at = time.monotonic()
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                if any(token in line for token in ("Error", "Exception", "Traceback", "RuntimeError")):
                    child_error = line[-1200:]
                emit({"event": "srt.voice.log", "data": line})
                continue
            if message.get("event") == "error":
                child_error = str(message.get("message") or message.get("error") or "")[-1200:]
            if message.get("event") == "startup":
                received_startup = True
            if message.get("item"):
                item = message["item"]
                by_id[int(item["id"])] = item
                manifest["items"] = [by_id[key] for key in sorted(by_id)]
                (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                job_state["items"] = manifest["items"]
                self._save_srt_job(job_state)
            emit({"event": "srt.voice.progress", "data": message})
        return_code = process.wait()
        if not cancelled and return_code != 0 and child_error:
            job_state.update({"state": "failed", "error": child_error})
            self._save_srt_job(job_state)
            self.srt_jobs.remove(job_id)
            raise RuntimeError(f"OmniVoice local lỗi: {child_error}")
        if not cancelled and return_code != 0:
            job_state.update({"state": "failed", "error": f"Mã thoát {return_code}"})
            self._save_srt_job(job_state)
            self.srt_jobs.remove(job_id)
            if return_code == 124:
                raise RuntimeError("OmniVoice bị treo khi khởi động PyTorch quá 3 phút. Hãy đóng tác vụ GPU khác rồi chạy lại.")
            raise RuntimeError(f"OmniVoice batch dừng với mã {return_code}")
        manifest["completedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        manifest["items"] = [by_id[key] for key in sorted(by_id)]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        requested_items = [by_id[key] for key in sorted(requested_ids) if key in by_id]
        completed = sum(1 for item in requested_items if item.get("status") == "completed")
        failed = sum(1 for item in requested_items if item.get("status") == "failed")
        final_state = "cancelled" if cancelled else "completed"
        job_state.update({"state": final_state, "items": requested_items, "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S")})
        self._save_srt_job(job_state)
        self.srt_jobs.remove(job_id)
        return {"state": final_state, "outputDir": str(output_dir), "manifestPath": str(manifest_path), "items": requested_items,
                "completed": completed, "failed": failed, "total": len(clean_entries)}

    def _srt_vieneu_generate(self, params: dict[str, Any], entries: list[Any]) -> dict[str, Any]:
        python = VIENEU_RUNTIME / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise RuntimeError("VieNeu-TTS is not installed. Run setup_vieneu_backend.bat first")
        output_dir = Path(str(params.get("outputDir", ""))).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        base_model = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
        codec_model = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano"
        if not self._is_model_downloaded(base_model):
            raise RuntimeError(f"Chưa tải Model VieNeu-TTS ({base_model})! Vui lòng vào Cấu hình ⚙️ ➔ Tải Model để bắt đầu tạo giọng.")
        if not self._is_model_downloaded(codec_model):
            raise RuntimeError(f"Chưa tải codec VieNeu-TTS v3 ({codec_model}). Hãy tải MOSS Audio Tokenizer trong Cấu hình.")
        clean_entries = []
        for position, raw in enumerate(entries, 1):
            if not isinstance(raw, dict) or not str(raw.get("text", "")).strip():
                continue
            clean_entries.append({**raw, "id": int(raw.get("id", position)), "text": str(raw["text"]).strip()})
        if not clean_entries:
            raise ValueError("No valid subtitle entries for VieNeu")

        job_id = str(params.get("jobId") or f"srt-{int(time.time()*1000)}")
        job_dir = self.user_data / "jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        job_path = job_dir / f"vieneu_{int(time.time()*1000)}.json"
        control_path = job_path.with_suffix(".control.json")
        control_path.write_text(json.dumps({"state": "running"}), encoding="utf-8")
        job = {
            "outputDir": str(output_dir), "entries": clean_entries,
            "baseModel": str(self.models.snapshot_path(base_model)),
            "codecModel": str(self.models.snapshot_path(codec_model)),
            "voice": str(params.get("vieneuVoice") or "Ngọc Lan"),
            "batchSize": min(32, max(1, int(params.get("vieneuBatchSize", 8)))),
            "speed": float(params.get("speed", 1.0)),
            "skipExisting": bool(params.get("skipExisting", True)),
        }
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        control = self.srt_jobs.register(job_id, control_path)
        helper = ROOT / "backend" / "engines" / "vieneu_srt_batch.py"
        process = subprocess.Popen(
            [str(python), str(helper), "--job", str(job_path), "--control", str(control_path)],
            cwd=str(VIENEU_RUNTIME), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        state = {
            "jobId": job_id, "state": "running", "engine": "vieneu", "provider": "local",
            "model": base_model, "voiceId": job["voice"], "workers": job["batchSize"],
            "outputDir": str(output_dir), "entries": clean_entries, "items": [],
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._save_srt_job(state)
        emit({"event": "srt.voice.job", "data": {"jobId": job_id, "state": "running"}})
        by_id: dict[int, dict[str, Any]] = {}
        final_state = "completed"
        child_error = ""
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                if any(token in line for token in ("Error", "Exception", "Traceback", "RuntimeError")):
                    child_error = line[-1200:]
                emit({"event": "srt.voice.log", "data": line})
                continue
            if message.get("event") == "error":
                child_error = str(message.get("message") or message.get("error") or "")[-1200:]
            if message.get("item"):
                item = message["item"]
                by_id[int(item["id"])] = item
                state["items"] = [by_id[key] for key in sorted(by_id)]
                self._save_srt_job(state)
            if message.get("event") == "complete":
                final_state = str(message.get("state", "completed"))
            emit({"event": "srt.voice.progress", "data": message})
        return_code = process.wait()
        self.srt_jobs.remove(job_id)
        if return_code != 0 and child_error:
            raise RuntimeError(f"VieNeu local lỗi: {child_error}")
        if return_code != 0:
            raise RuntimeError(f"VieNeu batch stopped with code {return_code}; check backend log")
        items = [by_id[key] for key in sorted(by_id)]
        state.update({"state": final_state, "items": items, "completedAt": time.strftime("%Y-%m-%dT%H:%M:%S")})
        self._save_srt_job(state)
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "jobId": job_id, "state": final_state, "outputDir": str(output_dir),
            "manifestPath": str(manifest_path), "items": items,
            "completed": sum(x.get("status") == "completed" for x in items),
            "failed": sum(x.get("status") == "failed" for x in items), "total": len(clean_entries),
        }

    def studio_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.voice_studio.generate(params)
        text = str(params.get("text", "")).strip()
        voice_id = str(params.get("voiceId", "")).strip()
        if not text:
            raise ValueError("Vui lòng nhập nội dung cần tạo giọng")
        if len(text) > 100_000:
            raise ValueError("Nội dung vượt quá 100.000 ký tự")
        if self._voice_config()["mode"] == "colab":
            voice_id = str(params.get("voiceId", "")).strip(); generation_id = f"studio_{int(time.time() * 1000)}"
            output_path = self.user_data / "outputs" / f"{generation_id}.wav"
            generated = self._remote_generate(text, voice_id, params, output_path)
            record = {"id": generation_id, "path": str(output_path), "name": output_path.name, "bytes": output_path.stat().st_size,
                      **generated, "format": "wav", "voiceId": voice_id,
                      "voiceName": next((v["name"] for v in self.voice_list({}) if v["id"] == voice_id), voice_id),
                      "language": str(params.get("language", "vi")), "text": text, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
            history_path = self.user_data / "studio-history.json"
            try: history = json.loads(history_path.read_text(encoding="utf-8"))
            except (OSError, ValueError): history = []
            history.insert(0, record); history_path.write_text(json.dumps(history[:100], ensure_ascii=False, indent=2), encoding="utf-8")
            return record
        voice_dir = LEGACY_OMNIVOICE / "voices" / voice_id
        if not (voice_dir / "profile.json").is_file():
            raise ValueError("Giọng đã chọn chưa có hồ sơ OmniVoice hoàn chỉnh")
        python = LEGACY_OMNIVOICE / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            raise RuntimeError("Không tìm thấy Python của D:\\OmniVoice")
        output_dir = self.user_data / "outputs"
        generation_id = f"studio_{int(time.time() * 1000)}"
        output_path = output_dir / f"{generation_id}.wav"
        seed_value = params.get("seed")
        seed = int(seed_value) if str(seed_value or "").strip() else int(time.time_ns() % 2_147_483_647)
        started = time.perf_counter()
        helper = ROOT / "backend" / "engines" / "omnivoice_generate.py"
        command = [str(python), str(helper), "--text", text, "--voice-dir", str(voice_dir),
                   "--output", str(output_path), "--language", str(params.get("language", "vi")),
                   "--speed", str(float(params.get("speed", 1.0))),
                   "--steps", str(int(params.get("steps", 32))),
                   "--guidance", str(float(params.get("guidance", 2.0))),
                   "--seed", str(seed)]
        if bool(params.get("denoise", True)):
            command.append("--denoise")
        if bool(params.get("postprocess", True)):
            command.append("--postprocess")
        completed = subprocess.run(command, cwd=str(LEGACY_OMNIVOICE), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=1800,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"Mã lỗi {completed.returncode}"
            raise RuntimeError(f"OmniVoice không thể tạo audio: {detail[-1200:]}")
        if not output_path.is_file():
            raise RuntimeError("OmniVoice hoàn tất nhưng không tạo file audio")
        with wave.open(str(output_path), "rb") as wav:
            duration = wav.getnframes() / max(1, wav.getframerate())
        record = {
            "id": generation_id, "path": str(output_path), "name": output_path.name,
            "bytes": output_path.stat().st_size, "duration": round(duration, 2),
            "generationTime": round(time.perf_counter() - started, 2), "seed": seed, "format": "wav",
            "voiceId": voice_id, "voiceName": next((v["name"] for v in self.voice_list({}) if v["id"] == voice_id), voice_id),
            "language": str(params.get("language", "vi")), "text": text,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if bool(params.get("createSrt")):
            srt_path = output_path.with_suffix(".srt")
            srt_path.write_text(build_srt(text, duration), encoding="utf-8")
            record["srtPath"] = str(srt_path)
        history = self._load_history()
        history.insert(0, record)
        self._history_path().write_text(json.dumps(history[:100], ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def _history_path(self) -> Path:
        return self.user_data / "studio-history.json"

    def _load_history(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._history_path().read_text(encoding="utf-8"))
            return [item for item in data if isinstance(item, dict) and Path(str(item.get("path", ""))).is_file()]
        except (OSError, ValueError, TypeError):
            return []

    def studio_history(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.voice_studio.history()

    def studio_history_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.voice_studio.delete_history(str(params.get("id", "")))
        generation_id = str(params.get("id", ""))
        history = self._load_history()
        remaining = [item for item in history if str(item.get("id")) != generation_id]
        self._history_path().write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"deleted": len(remaining) != len(history)}

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        try:
            method = str(request["method"])
            if method not in self.routes:
                raise LookupError(f"Unknown method: {method}")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            params = sanitize_json_value(params)
            return {"jsonrpc": "2.0", "id": request_id, "result": self.routes[method](params)}
        except Exception as exc:  # protocol boundary
            error = rpc_error(exc)
            if error["code"] == -32000:
                logging.exception("Request failed")
            else:
                logging.warning("Request rejected (%s): %s", error["data"]["kind"], error["message"])
            return {"jsonrpc": "2.0", "id": request_id, "error": error}


def normalize_language(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"vi", "vietnamese", "tiếng việt"}:
        return "Tiếng Việt"
    if raw in {"en", "english"}:
        return "English"
    return str(value or "Chưa xác định")


def slugify(value: str) -> str:
    import unicodedata
    cleaned = value.replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    result = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return result or f"voice-{int(time.time())}"


def build_srt(text: str, duration: float) -> str:
    chunks = [part.strip() for part in re.split(r"(?<=[.!?…])\s+|\n+", text) if part.strip()] or [text]
    weights = [max(1, len(part)) for part in chunks]
    total = sum(weights)
    cursor = 0.0
    blocks = []
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


EMIT_LOCK = threading.Lock()

def emit(message: dict[str, Any]) -> None:
    # ASCII JSON keeps the stdio protocol safe even if pasted text contains a lone UTF-16 surrogate.
    with EMIT_LOCK:
        sys.stdout.write(json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_json_value(item) for key, item in value.items()}
    return value


def self_test() -> int:
    worker = Worker(ROOT / ".dev-user-data")
    assert worker.handle({"id": "1", "method": "system.ping", "params": {}})["result"]["online"]
    voices = worker.voice_list({})
    assert isinstance(voices, list)
    assert "\udc8d" not in sanitize_json_value("lỗi\udc8dunicode")
    print(json.dumps({"ok": True, "voices": len(voices), "projects": len(worker.project_list({}))}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data", type=Path, default=ROOT / ".dev-user-data")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    worker = Worker(args.user_data)
    emit({"event": "backend.state", "data": {"online": True}})
    with ThreadPoolExecutor(max_workers=8) as rpc_pool:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                rpc_pool.submit(lambda value=request: emit(worker.handle(value)))
            except json.JSONDecodeError as exc:
                emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
