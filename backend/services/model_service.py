from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {"id": "omnivoice", "repo": "k2-fsa/OmniVoice", "name": "OmniVoice Core Model", "size": "1.8 GB",
     "description": "Model nhân bản và giả lập giọng nói chính cho chế độ local.", "required": True, "engine": "omnivoice"},
    {"id": "vieneu-v3-turbo", "repo": "pnnbao-ump/VieNeu-TTS-v3-Turbo", "name": "VieNeu-TTS v3 Turbo", "size": "1.5 GB",
     "description": "Model VieNeu mới nhất, 48 kHz, 10 giọng tích hợp và batch GPU tới 32.", "required": True, "engine": "vieneu"},
    {"id": "vieneu-moss-codec", "repo": "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano", "name": "MOSS Audio Tokenizer Nano", "size": "1 GB",
     "description": "Audio codec bắt buộc cho VieNeu-TTS v3 Turbo.", "required": True, "engine": "vieneu"},
    {"id": "sensevoice", "repo": "FunAudioLLM/SenseVoiceSmall", "name": "SenseVoice ASR Model", "size": "950 MB",
     "description": "Model nhận dạng lời nói từ audio tham chiếu.", "required": False, "engine": "asr"},
    {"id": "kokoro", "repo": "hexgrad/Kokoro-82M", "name": "Kokoro-82M TTS Model", "size": "320 MB",
     "description": "Model đọc văn bản offline tốc độ cao.", "required": False, "engine": "kokoro"},
)


class ModelService:
    def __init__(self, app_root: Path, emit: Callable[[dict[str, Any]], None], cache_root: Path | None = None):
        self.app_root = app_root
        self.emit = emit
        self.cache_root = (cache_root or (Path.home() / ".cache" / "huggingface" / "hub")).resolve()
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def hub_dir(self, repo_id: str) -> Path:
        folder = "models--" + repo_id.replace("/", "--")
        target = (self.cache_root / folder).resolve()
        if self.cache_root != target and self.cache_root not in target.parents:
            raise ValueError("Đường dẫn model nằm ngoài Hugging Face cache")
        return target

    def is_downloaded(self, repo_id: str) -> bool:
        snapshots = self.hub_dir(repo_id) / "snapshots"
        if not snapshots.is_dir():
            return False
        try:
            return any(snapshot.is_dir() and any(snapshot.iterdir()) for snapshot in snapshots.iterdir())
        except OSError:
            return False

    def snapshot_path(self, repo_id: str) -> Path:
        """Return the newest complete local snapshot without contacting the Hub."""
        snapshots = self.hub_dir(repo_id) / "snapshots"
        if not snapshots.is_dir():
            raise FileNotFoundError(f"Model chưa được tải đầy đủ: {repo_id}")
        candidates = sorted(
            (item for item in snapshots.iterdir() if item.is_dir() and any(item.iterdir())),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(f"Model chưa được tải đầy đủ: {repo_id}")
        return candidates[0].resolve()

    @staticmethod
    def directory_size(path: Path) -> str:
        if not path.exists():
            return "0 MB"
        try:
            total = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
            return f"{total / (1024 ** 3):.2f} GB" if total >= 1024 ** 3 else f"{total / (1024 ** 2):.1f} MB"
        except OSError:
            return "N/A"

    def list_models(self) -> list[dict[str, Any]]:
        with self._lock:
            active = set(self._active)
        result = []
        for item in MODEL_CATALOG:
            downloaded = self.is_downloaded(item["repo"])
            model_path = self.hub_dir(item["repo"])
            result.append({
                **item,
                "ready": downloaded,
                "status": "downloading" if item["id"] in active else ("ready" if downloaded else "not_downloaded"),
                "sizeOnDisk": self.directory_size(model_path) if downloaded else "0 MB",
                "localPath": str(model_path) if downloaded else None,
            })
        return result

    def _target(self, model_id: str) -> dict[str, Any]:
        target = next((item for item in MODEL_CATALOG if item["id"] == model_id), None)
        if not target:
            raise ValueError("Model không tồn tại trong danh mục")
        return target

    def download(self, model_id: str) -> dict[str, Any]:
        target = self._target(model_id)
        with self._lock:
            if model_id in self._active:
                return {"status": "downloading", "message": "Model đang được tải trong nền..."}
            self._active.add(model_id)

        def run_download() -> None:
            self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "downloading", "message": f"Bắt đầu tải {target['name']}..."}})
            try:
                process = subprocess.Popen(
                    [sys.executable, str(self.app_root / "backend" / "engines" / "download_model.py"), target["repo"]],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdout is not None
                completed_event = False
                for line in process.stdout:
                    rendered = line.strip()
                    if not rendered:
                        continue
                    try:
                        data = json.loads(rendered)
                    except ValueError:
                        logging.info("Model download output: %s", rendered)
                        continue
                    event = data.get("event")
                    message = data.get("message") or data.get("error") or ""
                    if event in {"start", "info", "downloading"}:
                        self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "downloading", "message": message}})
                    elif event == "completed":
                        completed_event = True
                        self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "ready", "message": f"Tải thành công {target['name']}!"}})
                    elif event == "error":
                        self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "error", "message": str(message)}})
                return_code = process.wait()
                if return_code != 0:
                    raise RuntimeError(f"Tiến trình tải model dừng với mã {return_code}")
                if not completed_event:
                    self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "ready", "message": f"Tải thành công {target['name']}!"}})
            except Exception as exc:
                self.emit({"event": "model.progress", "data": {"modelId": model_id, "status": "error", "message": str(exc)}})
            finally:
                with self._lock:
                    self._active.discard(model_id)

        threading.Thread(target=run_download, daemon=True, name=f"model-download-{model_id}").start()
        return {"status": "started", "modelId": model_id}

    def delete(self, model_id: str) -> dict[str, Any]:
        target = self._target(model_id)
        with self._lock:
            if model_id in self._active:
                raise RuntimeError("Không thể xóa model đang được tải")
        model_path = self.hub_dir(target["repo"])
        existed = model_path.exists()
        if existed:
            shutil.rmtree(model_path)
        if model_path.exists():
            raise RuntimeError("Không thể xóa hoàn toàn model khỏi cache")
        return {"ok": True, "modelId": model_id, "deleted": existed}
