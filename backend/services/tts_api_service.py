from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from backend.services.settings_service import SettingsService
from backend.services.capcut_tts_client import BUILTIN_VOICES, synthesize as capcut_synthesize


class TtsApiService:
    CAPCUT_SPACE_URL = "https://tony2k-ai-voice-studio.hf.space"

    def __init__(self, settings: SettingsService):
        self.settings = settings

    @staticmethod
    def _cancelled(control: dict[str, Any] | None) -> bool:
        return bool(control and control.get("cancel") and control["cancel"].is_set())

    def request_json(self, url: str, headers: dict[str, str], method: str = "GET",
                     fields: dict[str, Any] | None = None, timeout: int = 60,
                     control: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._cancelled(control):
            raise RuntimeError("Đã hủy tác vụ")
        data = None
        request_headers = {"User-Agent": "HHVietSub/0.1", **headers}
        if fields is not None:
            boundary = f"----HHVietSub{uuid.uuid4().hex}"
            body = bytearray()
            for key, value in fields.items():
                rendered = str(value).lower() if isinstance(value, bool) else str(value)
                body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{rendered}\r\n'.encode("utf-8"))
            body.extend(f"--{boundary}--\r\n".encode("ascii"))
            data = bytes(body)
            request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("Dịch vụ TTS trả dữ liệu không hợp lệ")
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API ({exc.code}): {detail[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Không thể kết nối dịch vụ TTS: {exc.reason}") from exc

    def request_json_body(self, url: str, fields: dict[str, Any], timeout: int = 180,
                          control: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._cancelled(control):
            raise RuntimeError("Đã hủy tác vụ")
        data = json.dumps(fields, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={
            "User-Agent": "HHVietSub/0.1", "Content-Type": "application/json; charset=utf-8",
        }, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("Dịch vụ CapCut TTS trả dữ liệu không hợp lệ")
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"CapCut Space ({exc.code}): {detail[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Không thể kết nối CapCut TTS Space: {exc.reason}") from exc

    def test_keys(self, provider: str, supplied: str = "") -> dict[str, Any]:
        if provider not in {"ai33", "aimax"}:
            raise ValueError("Nhà cung cấp API key không hợp lệ")
        if supplied:
            self.settings.save_tts({"ai33Key" if provider == "ai33" else "aimaxKey": supplied})
        keys = self.settings.tts_keys(provider)
        if not keys:
            raise ValueError(f"Chưa nhập API key {provider.upper()}")
        valid_count = 0
        errors = []
        for index, key in enumerate(keys, 1):
            try:
                if provider == "ai33":
                    self.request_json("https://api.ai33.pro/v3/voices?provider=edge&page=1&page_size=1", {"xi-api-key": key})
                else:
                    self.request_json("https://www.aimaxstudio.com/api/v1/voices?limit=1", {"X-API-Key": key})
                valid_count += 1
            except Exception as exc:
                errors.append(f"Key #{index}: {exc}")
        if valid_count == 0:
            raise ValueError(f"Tất cả {len(keys)} API key đều lỗi: {'; '.join(errors)}")
        return {"ok": True, "provider": provider, "totalKeys": len(keys), "validKeys": valid_count, "errors": errors}

    @staticmethod
    def voice_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload if all(isinstance(item, dict) for item in payload) else []
        if not isinstance(payload, dict):
            return []
        for key in ("voices", "items", "results", "data", "records"):
            found = TtsApiService.voice_records(payload.get(key))
            if found:
                return found
        return []

    def list_voices(self, engine: str, provider: str = "minimax", language: str = "auto") -> dict[str, Any]:
        engine, provider, language = engine.lower(), provider.lower(), language.strip()
        if engine == "capcut":
            records = BUILTIN_VOICES
            voices = []
            for raw in records:
                if not isinstance(raw, dict):
                    continue
                voice_type = str(raw.get("voice_type", "")).strip()
                resource_id = str(raw.get("resource_id", "")).strip()
                voice_language = str(raw.get("lang") or raw.get("lan") or "")
                if not voice_type or not resource_id:
                    continue
                if language and language.lower() != "auto":
                    expected = {
                        "vietnamese": "vi", "english": "en", "spanish": "es", "french": "fr",
                        "german": "de", "portuguese": "pt", "italian": "it", "japanese": "ja",
                        "korean": "ko", "chinese": "zh", "thai": "th", "indonesian": "id",
                        "russian": "ru", "arabic": "ar",
                    }.get(language.lower(), language.lower().split("-")[0])
                    if expected not in voice_language.lower():
                        continue
                voices.append({
                    "id": f"{voice_type}::{resource_id}",
                    "name": str(raw.get("display_name") or voice_type),
                    "previewUrl": "", "language": voice_language,
                    "provider": "capcut-direct", "personal": False,
                })
            return {"engine": engine, "provider": "capcut-direct", "language": language, "voices": voices, "total": len(voices)}
        keys = self.settings.tts_keys(engine)
        if not keys:
            raise ValueError(f"Chưa lưu API key {engine.upper()} trong Cấu hình")
        first_key = keys[0]
        if engine == "ai33":
            records = []
            for page in range(1, 21):
                fields: dict[str, Any] = {"provider": provider, "page": page, "page_size": 100}
                if language and language.lower() != "auto":
                    fields["language"] = language
                page_records = self.voice_records(self.request_json(
                    f"https://api.ai33.pro/v3/voices?{urlencode(fields)}", {"xi-api-key": first_key}
                ))
                records.extend(page_records)
                if len(page_records) < 100:
                    break
        elif engine == "aimax":
            headers = {"X-API-Key": first_key}
            records = []
            for page in range(10):
                payload = self.request_json(
                    f"https://www.aimaxstudio.com/api/v1/voices?{urlencode({'page': page, 'limit': 100})}", headers
                )
                records.extend(self.voice_records(payload))
                if not bool(payload.get("has_more")):
                    break
            records.extend(self.voice_records(self.request_json("https://www.aimaxstudio.com/api/v1/voices/my", headers)))
        else:
            raise ValueError("Dịch vụ thư viện giọng không hợp lệ")

        voices = []
        seen: set[str] = set()
        for raw in records:
            voice_id = str(raw.get("voice_id") or raw.get("voiceId") or raw.get("id") or raw.get("uuid") or "").strip()
            if not voice_id or voice_id in seen:
                continue
            source = raw.get("provider") or raw.get("source") or provider
            if engine == "aimax" and provider and str(source).lower() not in {provider, "", "none"} and not voice_id.startswith("uv_"):
                continue
            voices.append({
                "id": voice_id,
                "name": str(raw.get("name") or raw.get("voice_name") or raw.get("display_name") or raw.get("title") or voice_id),
                "previewUrl": str(raw.get("preview_url") or raw.get("previewUrl") or raw.get("generated_audio_cdn_url") or raw.get("audio_url") or raw.get("sample_url") or raw.get("demo_url") or ""),
                "language": str(raw.get("language") or raw.get("locale") or raw.get("lang") or ""),
                "provider": str(source), "personal": voice_id.startswith("uv_"),
            })
            seen.add(voice_id)
        return {"engine": engine, "provider": provider, "language": language, "voices": voices, "total": len(voices)}

    def preview(self, engine: str, url: str) -> dict[str, str]:
        if engine != "aimax" or not url:
            raise ValueError("Audio nghe thử không hợp lệ")
        keys = self.settings.tts_keys("aimax")
        if not keys:
            raise ValueError("Chưa lưu API key AIMax trong Cấu hình")
        full_url = urljoin("https://www.aimaxstudio.com", url)
        parsed = urlparse(full_url)
        if parsed.scheme != "https":
            raise ValueError("URL audio nghe thử phải dùng HTTPS")
        headers = {"User-Agent": "HHVietSub/0.1"}
        if parsed.hostname == "www.aimaxstudio.com":
            headers["X-API-Key"] = keys[0]
        try:
            with urllib.request.urlopen(urllib.request.Request(full_url, headers=headers), timeout=90) as response:
                audio = response.read()
                mime = response.headers.get_content_type() or "audio/mpeg"
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Không tải được audio nghe thử ({exc.code})") from exc
        if len(audio) > 25 * 1024 * 1024:
            raise RuntimeError("Audio nghe thử vượt quá giới hạn 25 MB")
        return {"dataUrl": f"data:{mime};base64,{base64.b64encode(audio).decode('ascii')}"}

    @staticmethod
    def download_audio(url: str, destination: Path, headers: dict[str, str] | None = None) -> float:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HHVietSub/0.1", **(headers or {})}), timeout=180) as response:
            audio = response.read()
        if len(audio) > 100 * 1024 * 1024:
            raise RuntimeError("Audio API vượt quá giới hạn 100 MB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if audio[:4] == b"RIFF":
            destination.write_bytes(audio)
        else:
            app_root = Path(os.environ.get("HHVIETSUB_APP_ROOT", "")).expanduser()
            bundled_ffmpeg = app_root / "vendor" / "ffmpeg" / "ffmpeg.exe"
            ffmpeg = str(bundled_ffmpeg) if bundled_ffmpeg.is_file() else shutil.which("ffmpeg")
            if not ffmpeg:
                try:
                    import imageio_ffmpeg
                    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                except (ImportError, RuntimeError):
                    ffmpeg = None
            if not ffmpeg:
                raise RuntimeError("Cần FFmpeg để chuyển audio API thành WAV")
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as temp:
                temp.write(audio)
                temp_path = Path(temp.name)
            try:
                subprocess.run([ffmpeg, "-y", "-i", str(temp_path), "-ac", "1", "-ar", "24000", str(destination)],
                               check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            finally:
                temp_path.unlink(missing_ok=True)
        with wave.open(str(destination), "rb") as wav:
            return wav.getnframes() / max(1, wav.getframerate())

    def generate_one(self, engine: str, entry: dict[str, Any], params: dict[str, Any], output: Path,
                     control: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._cancelled(control):
            raise RuntimeError("Đã hủy tác vụ")
        voice_id = str(params.get("apiVoiceId", "")).strip()
        if engine == "capcut":
            if "::" not in voice_id:
                raise ValueError("Hãy chọn một giọng từ thư viện CapCut")
            voice_type, resource_id = voice_id.split("::", 1)
            backend_mode = str(params.get("capcutBackend", "direct")).lower()
            if backend_mode == "hybrid":
                backend_mode = "direct" if int(entry.get("id", 1)) % 2 else "space"
            if backend_mode == "space":
                created = self.request_json_body(f"{self.CAPCUT_SPACE_URL}/api/tts", {
                    "text": str(entry.get("text", "")), "voice": voice_type,
                    "resource_id": resource_id,
                    "rate": min(3.0, max(.5, float(params.get("speed", 1.0)))),
                }, control=control)
                audio_url = str(created.get("speech_url", "")).strip()
                if not audio_url:
                    raise RuntimeError("CapCut Space không trả về URL audio")
                audio_url = urljoin(self.CAPCUT_SPACE_URL + "/", audio_url)
            else:
                audio_url = capcut_synthesize(
                    str(entry.get("text", "")), voice_type, resource_id,
                    float(params.get("speed", 1.0)),
                    cancelled=lambda: self._cancelled(control),
                )
            with urllib.request.urlopen(
                urllib.request.Request(audio_url, headers={"User-Agent": "HHVietSub/0.1"}),
                timeout=120,
            ) as response:
                audio = response.read()
            if len(audio) < 128 or audio.lstrip().startswith((b"<", b"{", b"[")):
                raise RuntimeError("CapCut trả về file MP3 không hợp lệ")
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".part")
            temporary.write_bytes(audio)
            temporary.replace(output)
            return {**entry, "status": "completed", "file": str(output), "duration": 0,
                    "format": "mp3", "engine": engine, "backend": backend_mode}
        keys = self.settings.tts_keys(engine)
        if not keys:
            raise ValueError(f"Chưa lưu API key {engine.upper()} trong Cấu hình")
        if not voice_id:
            raise ValueError("Chưa nhập Voice ID của dịch vụ API")
        speed = float(params.get("speed", 1.0))
        provider = str(params.get("apiProvider", "minimax"))
        model = str(params.get("apiModel", ""))
        entry_id = int(entry.get("id", 1))
        active_key = keys[(entry_id - 1) % len(keys)]
        if engine == "ai33":
            created = self.request_json("https://api.ai33.pro/v3/text-to-speech", {"xi-api-key": active_key}, "POST",
                                        {"text": entry["text"], "voice_id": voice_id, "speed": min(1.5, max(.5, speed)), "with_transcript": False}, control=control)
            job_id = created.get("task_id")
            poll_url, headers, base = f"https://api.ai33.pro/v1/task/{job_id}", {"xi-api-key": active_key}, "https://api.ai33.pro"
        elif engine == "aimax":
            safe_speed = min(1.2, max(.7, speed)) if provider == "elevenlabs" else min(2.0, max(.5, speed))
            fields: dict[str, Any] = {"provider": provider, "voice_id": voice_id, "text": entry["text"], "speed": safe_speed,
                                      "pitch": 0, "vol": 1.0, "model": model, "normalize": True, "enable_srt": False}
            selected_language = str(params.get("subtitleLanguage", "auto")).strip()
            if selected_language and selected_language.lower() != "auto":
                fields["language"] = selected_language
            elif provider != "elevenlabs":
                fields["language"] = "Vietnamese"
            if provider == "elevenlabs" and model != "eleven_v3":
                fields.update({"stability": .5, "similarity": .75, "style_exaggeration": .3, "use_speaker_boost": True})
            created = self.request_json("https://www.aimaxstudio.com/api/v1/tts/generate", {"X-API-Key": active_key}, "POST", fields, control=control)
            job_id = created.get("job_id")
            poll_url, headers, base = f"https://www.aimaxstudio.com/api/v1/tts/jobs/{job_id}", {"X-API-Key": active_key}, "https://www.aimaxstudio.com"
        else:
            raise ValueError("Dịch vụ TTS không hợp lệ")
        if not job_id:
            raise RuntimeError("Dịch vụ không trả về mã tác vụ")
        deadline, poll_interval = time.time() + 1800, 0.5
        while time.time() < deadline:
            if self._cancelled(control):
                raise RuntimeError("Đã hủy tác vụ")
            status = self.request_json(poll_url, headers, control=control)
            state = str(status.get("status", "")).lower()
            if state in {"done", "completed", "success", "succeeded"}:
                metadata = status.get("metadata") if isinstance(status.get("metadata"), dict) else {}
                audio_url = status.get("audio_url") or status.get("output_uri") or metadata.get("audio_url") or metadata.get("output_uri")
                if not audio_url:
                    raise RuntimeError("Tác vụ hoàn tất nhưng không có URL audio")
                duration = self.download_audio(urljoin(base, str(audio_url)), output, headers)
                return {**entry, "status": "completed", "file": str(output), "duration": round(duration, 2), "engine": engine}
            if state in {"failed", "error", "cancelled", "canceled"}:
                raise RuntimeError(str(status.get("error_message") or status.get("message") or "Tác vụ TTS thất bại"))
            for _ in range(max(1, int(poll_interval / 0.1))):
                if self._cancelled(control):
                    raise RuntimeError("Đã hủy tác vụ")
                time.sleep(0.1)
            poll_interval = min(2.0, poll_interval + 0.5)
        raise TimeoutError("Dịch vụ TTS quá thời gian chờ 30 phút")
