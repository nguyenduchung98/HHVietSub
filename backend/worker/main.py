from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
import wave
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.settings_service import SettingsService
from backend.services.tts_api_service import TtsApiService
from backend.services.srt_job_service import SrtJobService
from backend.services.subtitle_service import SubtitleService
from backend.rpc.errors import rpc_error


def app_version() -> str:
    try:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        return str(package.get("version") or "0.0.0")
    except (OSError, ValueError, TypeError):
        return "0.0.0"

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Worker:
    def __init__(self, user_data: Path):
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsService(self.user_data)
        self.tts_api = TtsApiService(self.settings)
        self.srt_jobs = SrtJobService(self.user_data, emit)
        self.ffmpeg_sync_lock = threading.Lock()
        self.routes: dict[str, Callable[[dict[str, Any]], Any]] = {
            "system.ping": self.ping,
            "project.list": self.project_list,
            "settings.secrets.export": self.secrets_export,
            "settings.secrets.set": self.secrets_set,
            "settings.tts.get": self.tts_settings_get,
            "settings.tts.save": self.tts_settings_save,
            "settings.tts.test": self.tts_settings_test,
            "tts.voices.list": self.tts_voices_list,
            "tts.voice.preview": self.tts_voice_preview,
            "subtitle.parse": self.subtitle_parse,
            "srt.voice.generate": self.srt_voice_generate,
            "srt.voice.regenerate": self.srt_voice_generate,
            "srt.voice.control": self.srt_voice_control,
            "srt.voice.latest": self.srt_voice_latest,
            "srt.voice.list": self.srt_voice_list,
            "srt.voice.get": self.srt_voice_get,
            "capcut.project.validate_existing": self.capcut_project_validate_existing,
            "capcut.project.sync": self.capcut_project_sync,
            "capcut.open": self.capcut_open,
            "ffmpeg.sync.validate": self.ffmpeg_sync_validate,
            "ffmpeg.sync.create": self.ffmpeg_sync_create,
        }

    def ping(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"online": True, "version": app_version(), "protocol": 1}




    def project_list(self, _params: dict[str, Any]) -> list[dict[str, str]]:
        try:
            from backend.engines.capcut_project_v1 import project_root
            root = project_root()
        except (OSError, RuntimeError, ValueError, ImportError):
            return []
        result: list[dict[str, str]] = []
        projects: list[tuple[float, Path]] = []
        for child in root.iterdir():
            try:
                if child.is_dir() and (child / "draft_content.json").is_file():
                    projects.append((child.stat().st_mtime, child))
            except OSError:
                continue
        for _modified_at, child in sorted(projects, key=lambda item: item[0], reverse=True):
            result.append({"name": child.name, "folder": child.name, "path": str(child)})
        return result[:100]









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




    def subtitle_parse(self, params: dict[str, Any]) -> dict[str, Any]:
        return SubtitleService.parse(Path(str(params.get("path", ""))))

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
            merge_audio = False
            return render(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
                          Path(str(params.get("voiceDir", ""))), output_dir,
                          str(params.get("projectName", "")), logger,
                          int(params.get("chunkPieces", 100)), encoder_choice=encoder,
                          voice_speed=voice_speed, change_pitch=change_pitch,
                          video_volume_db=video_volume_db, merge_audio=merge_audio)
        finally:
            self.ffmpeg_sync_lock.release()




    def srt_voice_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        entries = params.get("entries")
        engine = str(params.get("engine", "capcut")).lower()
        if not isinstance(entries, list) or not entries:
            raise ValueError("Kh?ng c? c?u ph? ?? ?? t?o gi?ng")
        if engine not in {"capcut", "ai33", "aimax"}:
            raise ValueError("HHVietSub Lite supports CapCut TTS, AI33 and AIMax")
        job_params = {**params, "jobId": str(params.get("jobId") or f"srt-{int(time.time() * 1000)}")}
        try:
            return self._srt_api_generate(engine, job_params, entries)
        finally:
            self.srt_jobs.remove(job_params["jobId"])







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
    voices = worker.tts_voices_list({"engine": "capcut", "language": "vi"})
    assert isinstance(voices, dict)
    assert "\udc8d" not in sanitize_json_value("lỗi\udc8dunicode")
    print(json.dumps({"ok": True, "voices": len(voices.get("voices", [])), "projects": len(worker.project_list({}))}, ensure_ascii=False))
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
