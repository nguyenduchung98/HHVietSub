from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import wave
import urllib.error
import urllib.request
import mimetypes
import uuid
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LEGACY_OMNIVOICE = Path(r"D:\OmniVoice")
LEGACY_CAPCUT = Path(r"D:\Dịch-Đồng Bộ\Dich_CapCut_v2")

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class Worker:
    def __init__(self, user_data: Path):
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.routes: dict[str, Callable[[dict[str, Any]], Any]] = {
            "system.ping": self.ping,
            "system.info": self.system_info,
            "voice.list": self.voice_list,
            "voice.create": self.voice_create,
            "project.list": self.project_list,
            "settings.get": self.settings_get,
            "settings.voice.save": self.voice_settings_save,
            "settings.voice.test": self.voice_settings_test,
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
            "capcut.project.validate": self.capcut_project_validate,
            "capcut.project.create": self.capcut_project_create,
            "capcut.open": self.capcut_open,
        }

    def ping(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"online": True, "version": "0.1.0-dev", "protocol": 1}

    def system_info(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"python": sys.version.split()[0], "user_data": str(self.user_data), "project_root": str(ROOT)}

    def voice_list(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        voices_dir = LEGACY_OMNIVOICE / "voices"
        voices: list[dict[str, Any]] = []
        if not voices_dir.exists():
            return voices
        for profile_path in sorted(voices_dir.glob("*/profile.json")):
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                audio = profile_path.parent / str(profile.get("ref_audio", ""))
                voices.append({
                    "id": profile_path.parent.name,
                    "name": str(profile.get("name") or profile_path.parent.name),
                    "language": normalize_language(profile.get("language")),
                    "ready": (profile_path.parent / str(profile.get("voice_prompt", "voice.pt"))).exists(),
                    "source": "OmniVoice",
                    "referenceAudio": str(audio) if audio.exists() else None,
                })
            except (OSError, ValueError, TypeError) as exc:
                logging.warning("Invalid voice profile %s: %s", profile_path, exc)
        for audio in sorted(voices_dir.iterdir()):
            if audio.is_file() and audio.suffix.lower() in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
                voices.append({"id": audio.stem.lower().replace(" ", "-"), "name": audio.stem, "language": "Chưa xác định", "ready": False, "source": "Legacy audio", "referenceAudio": str(audio)})
        return voices

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
        return {"omnivoiceRoot": str(LEGACY_OMNIVOICE), "legacyCapCutRoot": str(LEGACY_CAPCUT), "ttsEngine": "omnivoice", "voiceBackend": voice_config,
                "gemini": {"url": old.get("endpoint", ""), "saved": old.get("gem_links", []),
                            "selected": old.get("selected_gem_name", ""), "models": old.get("model_values", []),
                            "model": old.get("model", "3.1 Pro"), "batch": int(old.get("batch", 200)),
                            "workers": int(old.get("workers", 1)), "profileReady": profile_path.is_dir(),
                            "profilePath": str(profile_path)}}

    def _voice_config(self) -> dict[str, Any]:
        path = self.user_data / "voice-backend.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            value = {}
        return {"mode": "colab" if value.get("mode") == "colab" else "local",
                "url": str(value.get("url", "")).rstrip("/"), "token": str(value.get("token", ""))}

    def voice_settings_save(self, params: dict[str, Any]) -> dict[str, Any]:
        mode = "colab" if params.get("mode") == "colab" else "local"
        url = str(params.get("url", "")).strip().rstrip("/")
        if mode == "colab" and not url.startswith("https://"):
            raise ValueError("URL Colab phải bắt đầu bằng https://")
        value = {"mode": mode, "url": url, "token": str(params.get("token", "")).strip()}
        (self.user_data / "voice-backend.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return value

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
        path = Path(str(params.get("path", ""))).resolve()
        if path.suffix.lower() != ".srt" or not path.is_file():
            raise ValueError("Vui lòng chọn một file SRT hợp lệ")
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
        timestamp = re.compile(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})$")
        entries: list[dict[str, Any]] = []
        warnings: list[str] = []
        for position, block in enumerate(blocks, 1):
            lines = [line.rstrip() for line in block.splitlines()]
            if len(lines) < 2:
                warnings.append(f"Khối {position} không đủ dữ liệu")
                continue
            try:
                entry_id = int(lines[0].strip())
                time_line = lines[1].strip()
                text_lines = lines[2:]
            except ValueError:
                entry_id = position
                time_line = lines[0].strip()
                text_lines = lines[1:]
            match = timestamp.match(time_line)
            if not match:
                warnings.append(f"Khối {position} có timestamp không hợp lệ")
                continue
            text = "\n".join(text_lines).strip()
            entries.append({"id": entry_id, "start": match.group(1), "end": match.group(2), "source": text, "translated": ""})
        if not entries:
            raise ValueError("Không đọc được câu phụ đề nào trong file")
        return {"path": str(path), "name": path.name, "entries": entries, "warnings": warnings, "characters": sum(len(item["source"]) for item in entries)}

    def subtitle_save(self, params: dict[str, Any]) -> dict[str, Any]:
        source_path = Path(str(params.get("sourcePath", ""))).resolve()
        entries = params.get("entries")
        if source_path.suffix.lower() != ".srt" or not source_path.is_file():
            raise ValueError("File SRT nguồn không hợp lệ")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Không có dữ liệu phụ đề để lưu")
        output_value = str(params.get("outputPath", "")).strip()
        output_path = Path(output_value).resolve() if output_value else source_path.with_name(f"{source_path.stem}_vi.srt")
        blocks: list[str] = []
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                continue
            start, end = str(entry.get("start", "")), str(entry.get("end", ""))
            text = str(entry.get("translated") or entry.get("source") or "").strip()
            blocks.append(f"{index}\n{start} --> {end}\n{text}")
        output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        return {"path": str(output_path), "entries": len(blocks)}

    def subtitle_translate(self, params: dict[str, Any]) -> dict[str, Any]:
        api_key = str(params.get("apiKey", "")).strip()
        model = str(params.get("model", "gemini-3.5-flash")).strip()
        source_language = str(params.get("sourceLanguage", "Auto")).strip()
        target_language = str(params.get("targetLanguage", "Tiếng Việt")).strip()
        glossary = str(params.get("glossary", "")).strip()
        entries = params.get("entries")
        if not api_key:
            raise ValueError("Vui lòng nhập Gemini API key")
        if not re.fullmatch(r"gemini-[a-zA-Z0-9._-]+", model):
            raise ValueError("Tên model Gemini không hợp lệ")
        if not isinstance(entries, list) or not entries or len(entries) > 40:
            raise ValueError("Mỗi lượt dịch phải có từ 1 đến 40 câu")
        input_rows = [{"id": int(item.get("id", index + 1)), "text": str(item.get("text", ""))}
                      for index, item in enumerate(entries) if isinstance(item, dict)]
        prompt = (
            f"Bạn là biên dịch viên phụ đề chuyên nghiệp. Dịch từ {source_language} sang {target_language}. "
            "Giữ nguyên ý nghĩa, tên riêng, con số và ký hiệu định dạng. Viết tự nhiên, súc tích để đọc trên màn hình. "
            "Không thêm giải thích. Trả đúng một bản dịch cho mỗi id và giữ nguyên id."
        )
        if glossary:
            prompt += f"\nThuật ngữ bắt buộc áp dụng:\n{glossary}"
        prompt += "\nDữ liệu cần dịch:\n" + json.dumps(input_rows, ensure_ascii=False)
        schema = {
            "type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "id": {"type": "INTEGER"}, "translated": {"type": "STRING"}},
                "required": ["id", "translated"]}}
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {
            "temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema}}
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("error", {}).get("message", detail)
            except ValueError:
                message = detail
            raise RuntimeError(f"Gemini API: {message[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Không kết nối được Gemini API: {exc.reason}") from exc
        try:
            raw = payload["candidates"][0]["content"]["parts"][0]["text"]
            translated = json.loads(raw)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Gemini trả về dữ liệu không đúng định dạng") from exc
        expected = {item["id"] for item in input_rows}
        results = []
        for item in translated if isinstance(translated, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                item_id = int(item.get("id", -1))
            except (TypeError, ValueError):
                continue
            if item_id in expected:
                results.append({"id": item_id, "translated": str(item.get("translated", "")).strip()})
        return {"results": results, "requested": len(input_rows), "translated": len(results)}

    def subtitle_translate_browser(self, params: dict[str, Any]) -> dict[str, Any]:
        legacy_root = LEGACY_CAPCUT
        if str(legacy_root) not in sys.path:
            sys.path.insert(0, str(legacy_root))
        import services.translator_service as translator_service  # type: ignore
        from services.translator_service import (  # type: ignore
            BrowserConfig, DEFAULT_INSTRUCTION, SeleniumGeminiTranslator,
            chunk_entries, translate_chunk_with_retries,
        )
        entries = params.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Không có câu phụ đề để dịch")
        config_path = legacy_root / "config.json"
        old_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        gem_url = str(params.get("gemUrl") or old_config.get("endpoint") or "").strip()
        if not gem_url.startswith("https://gemini.google.com/"):
            raise ValueError("Link Gem không hợp lệ")
        batch_size = max(1, min(300, int(params.get("batchSize", old_config.get("batch", 200)))))
        model_name = str(params.get("modelName") or old_config.get("model") or "").strip()
        profile_value = Path(str(old_config.get("chrome_profile", "../chrome_profile")))
        profile_path = profile_value if profile_value.is_absolute() else (legacy_root / profile_value).resolve()
        workers = max(1, min(5, int(params.get("workers", old_config.get("workers", 1)))))
        cfg = BrowserConfig(gem_url=gem_url, workers=workers, model_name=model_name,
                            user_data_dir=str(profile_path),
                            profile_directory=str(old_config.get("profile_dir", "Default")))
        source_entries = [{"id": int(item.get("id", index + 1)), "source": str(item.get("text", ""))}
                          for index, item in enumerate(entries) if isinstance(item, dict)]
        source_language = str(params.get("sourceLanguage", "Auto"))
        target_language = str(params.get("targetLanguage", "Tiếng Việt"))
        glossary = str(params.get("glossary", "")).strip()
        instruction = f"Dịch từ {source_language} sang {target_language}.\n" + DEFAULT_INSTRUCTION
        if glossary:
            instruction += "\nThuật ngữ bổ sung bắt buộc:\n" + glossary
        original_builder = translator_service.build_chunk_text
        translator_service.build_chunk_text = lambda chunk, rule=instruction: rule + "\n\n" + original_builder(chunk, rule)
        chunks = chunk_entries(source_entries, batch_size)
        translator = SeleniumGeminiTranslator(config=cfg, logger=lambda message: logging.info("Gemini: %s", message))
        results: dict[int, str] = {}
        try:
            translator.open()
            tasks: queue.Queue[tuple[int, list[dict[str, Any]]]] = queue.Queue()
            for chunk_index, chunk in enumerate(chunks, 1):
                tasks.put((chunk_index, chunk))
            def run_tab(tab_index: int) -> None:
                while True:
                    try:
                        chunk_index, chunk = tasks.get_nowait()
                    except queue.Empty:
                        return
                    try:
                        logging.info("Translating Gemini chunk %s/%s on tab %s", chunk_index, len(chunks), tab_index + 1)
                        translated = translate_chunk_with_retries(
                            translator=translator, chunk=chunk, instruction=instruction,
                            tab_index=tab_index, max_retries=3, logger=lambda message: logging.info("Gemini: %s", message))
                        results.update(translated)
                    finally:
                        tasks.task_done()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(run_tab, index) for index in range(workers)]
                for future in futures:
                    future.result()
        finally:
            translator.close()
        return {"results": [{"id": item_id, "translated": text} for item_id, text in sorted(results.items())],
                "requested": len(source_entries), "translated": len(results), "chunks": len(chunks)}

    def capcut_project_validate(self, params: dict[str, Any]) -> dict[str, Any]:
        from backend.engines.capcut_project_v1 import validate_inputs
        return validate_inputs(Path(str(params.get("videoPath", ""))), Path(str(params.get("srtPath", ""))),
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

    def _voice_reference(self, voice_id: str) -> tuple[Path, dict[str, Any]]:
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

    def srt_voice_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        entries = params.get("entries")
        voice_id = str(params.get("voiceId", "")).strip()
        if not isinstance(entries, list) or not entries:
            raise ValueError("Không có câu phụ đề để tạo giọng")
        if self._voice_config()["mode"] == "colab":
            voice_id = str(params.get("voiceId", "")).strip()
            output_value = str(params.get("outputDir", "")).strip()
            output_dir = Path(output_value).resolve() if output_value else self.user_data / "srt-voice-output"
            output_dir.mkdir(parents=True, exist_ok=True); items = []
            for position, entry in enumerate(entries, 1):
                if not isinstance(entry, dict) or not str(entry.get("text", "")).strip(): continue
                item_id = int(entry.get("id", position)); output = output_dir / f"{item_id:04d}.wav"; result = None; error = ""
                if bool(params.get("skipExisting", True)) and output.is_file():
                    with wave.open(str(output), "rb") as wav: duration = wav.getnframes() / max(1, wav.getframerate())
                    result = {"duration": round(duration, 2)}
                else:
                    for attempt in range(3):
                        try:
                            emit({"event": "srt.voice.progress", "data": {"done": len(items), "total": len(entries), "current": item_id, "attempt": attempt + 1}})
                            result = self._remote_generate(str(entry["text"]).strip(), voice_id, params, output); break
                        except Exception as exc: error = str(exc)
                item = {**entry, "id": item_id, "status": "completed" if result else "failed", "file": str(output) if result else None,
                        "duration": result["duration"] if result else None, "error": error}
                items.append(item); emit({"event": "srt.voice.progress", "data": {"done": len(items), "total": len(entries), "item": item}})
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
            "language": str(params.get("language", "vi")), "speed": float(params.get("speed", 1.0)),
            "steps": int(params.get("steps", 32)), "guidance": float(params.get("guidance", 2.0)),
            "seed": params.get("seed"), "denoise": bool(params.get("denoise", False)),
            "postprocess": bool(params.get("postprocess", True)),
            "skipExisting": bool(params.get("skipExisting", True)),
        }
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        helper = ROOT / "backend" / "engines" / "omnivoice_srt_batch.py"
        command = [str(python), str(helper), "--job", str(job_path)]
        process = subprocess.Popen(command, cwd=str(LEGACY_OMNIVOICE), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        manifest_path = output_dir / "manifest.json"
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            previous_items = previous_manifest.get("items", []) if isinstance(previous_manifest, dict) else []
        except (OSError, ValueError, TypeError):
            previous_items = []
        manifest = {"voiceId": voice_id, "outputDir": str(output_dir), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": []}
        by_id: dict[int, dict[str, Any]] = {int(item["id"]): item for item in previous_items if isinstance(item, dict) and "id" in item}
        requested_ids = {int(entry["id"]) for entry in clean_entries}
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                emit({"event": "srt.voice.log", "data": line})
                continue
            if message.get("item"):
                item = message["item"]
                by_id[int(item["id"])] = item
                manifest["items"] = [by_id[key] for key in sorted(by_id)]
                (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            emit({"event": "srt.voice.progress", "data": message})
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"OmniVoice batch dừng với mã {return_code}")
        manifest["completedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        manifest["items"] = [by_id[key] for key in sorted(by_id)]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        requested_items = [by_id[key] for key in sorted(requested_ids) if key in by_id]
        completed = sum(1 for item in requested_items if item.get("status") == "completed")
        failed = sum(1 for item in requested_items if item.get("status") == "failed")
        return {"outputDir": str(output_dir), "manifestPath": str(manifest_path), "items": requested_items,
                "completed": completed, "failed": failed, "total": len(clean_entries)}

    def studio_generate(self, params: dict[str, Any]) -> dict[str, Any]:
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
        return self._load_history()

    def studio_history_delete(self, params: dict[str, Any]) -> dict[str, Any]:
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
                raise ValueError(f"Unknown method: {method}")
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            params = sanitize_json_value(params)
            return {"jsonrpc": "2.0", "id": request_id, "result": self.routes[method](params)}
        except Exception as exc:  # protocol boundary
            logging.exception("Request failed")
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}


def normalize_language(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"vi", "vietnamese", "tiếng việt"}:
        return "Tiếng Việt"
    if raw in {"en", "english"}:
        return "English"
    return str(value or "Chưa xác định")


def slugify(value: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
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


def emit(message: dict[str, Any]) -> None:
    # ASCII JSON keeps the stdio protocol safe even if pasted text contains a lone UTF-16 surrogate.
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
    for line in sys.stdin:
        try:
            request = json.loads(line)
            emit(worker.handle(request))
        except json.JSONDecodeError as exc:
            emit({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
