from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SettingsService:
    """Owns non-secret settings and the worker's in-memory decrypted secrets."""

    def __init__(self, user_data: Path):
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.voice_token = ""
        self.tts_api_secrets = {"ai33Key": "", "aimaxKey": ""}
        self._load_legacy_secrets()

    @property
    def voice_path(self) -> Path:
        return self.user_data / "voice-backend.json"

    @property
    def tts_path(self) -> Path:
        return self.user_data / "tts-api-settings.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def parse_keys(raw: str) -> list[str]:
        if not raw or not isinstance(raw, str):
            return []
        return [token.strip() for token in re.split(r"[\n\r,;]+", raw) if token.strip()]

    def _load_legacy_secrets(self) -> None:
        voice_value = self._read_json(self.voice_path)
        tts_value = self._read_json(self.tts_path)
        self.voice_token = str(voice_value.get("token", "")).strip()
        self.tts_api_secrets = {
            "ai33Key": str(tts_value.get("ai33Key", "")).strip(),
            "aimaxKey": str(tts_value.get("aimaxKey", "")).strip(),
        }

    def voice_config(self, *, include_secret: bool = True) -> dict[str, Any]:
        value = self._read_json(self.voice_path)
        return {
            "mode": "colab" if value.get("mode") == "colab" else "local",
            "url": str(value.get("url", "")).rstrip("/"),
            "token": self.voice_token if include_secret else "",
            "tokenConfigured": bool(self.voice_token),
        }

    def save_voice(self, params: dict[str, Any]) -> dict[str, Any]:
        mode = "colab" if params.get("mode") == "colab" else "local"
        url = str(params.get("url", "")).strip().rstrip("/")
        if mode == "colab" and not url.startswith("https://"):
            raise ValueError("URL Colab phải bắt đầu bằng https://")
        supplied_token = str(params.get("token", "")).strip()
        if supplied_token:
            self.voice_token = supplied_token
        self._write_json(self.voice_path, {"mode": mode, "url": url})
        return self.voice_config(include_secret=False)

    def export_secrets(self) -> dict[str, str]:
        return {"voiceToken": self.voice_token, **self.tts_api_secrets}

    def set_secrets(self, params: dict[str, Any]) -> dict[str, Any]:
        if "voiceToken" in params:
            self.voice_token = str(params.get("voiceToken", "")).strip()
        for key in ("ai33Key", "aimaxKey"):
            if key in params:
                self.tts_api_secrets[key] = str(params.get(key, "")).strip()
        voice = self.voice_config()
        self._write_json(self.voice_path, {"mode": voice["mode"], "url": voice["url"]})
        self._write_json(self.tts_path, {})
        return {
            "voiceTokenConfigured": bool(self.voice_token),
            "ai33KeyCount": len(self.parse_keys(self.tts_api_secrets["ai33Key"])),
            "aimaxKeyCount": len(self.parse_keys(self.tts_api_secrets["aimaxKey"])),
        }

    def tts_config(self) -> dict[str, str]:
        return dict(self.tts_api_secrets)

    def tts_keys(self, provider: str) -> list[str]:
        key = "ai33Key" if provider == "ai33" else "aimaxKey"
        return self.parse_keys(self.tts_api_secrets.get(key, ""))

    def tts_status(self) -> dict[str, Any]:
        ai33_keys = self.tts_keys("ai33")
        aimax_keys = self.tts_keys("aimax")
        return {
            "ai33Configured": bool(ai33_keys),
            "aimaxConfigured": bool(aimax_keys),
            "ai33KeyCount": len(ai33_keys),
            "aimaxKeyCount": len(aimax_keys),
        }

    def save_tts(self, params: dict[str, Any]) -> dict[str, Any]:
        for key in ("ai33Key", "aimaxKey"):
            supplied = str(params.get(key, "")).strip()
            if supplied:
                self.tts_api_secrets[key] = supplied
        return self.tts_status()
