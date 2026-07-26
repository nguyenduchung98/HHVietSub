from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable


JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")


class SrtJobService:
    def __init__(self, user_data: Path, emit: Callable[[dict[str, Any]], None], retention: int = 100):
        self.folder = user_data / "srt-jobs"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.emit = emit
        self.retention = max(10, retention)
        self._controls: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def validate_job_id(job_id: str) -> str:
        if not JOB_ID_RE.fullmatch(job_id):
            raise ValueError("Job ID chỉ được chứa chữ, số, dấu gạch ngang hoặc gạch dưới")
        return job_id

    def path(self, job_id: str) -> Path:
        return self.folder / f"{self.validate_job_id(job_id)}.json"

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def save(self, job: dict[str, Any]) -> None:
        job_id = self.validate_job_id(str(job.get("jobId", "")))
        self._atomic_json(self.path(job_id), job)
        self._prune()

    def latest(self) -> dict[str, Any] | None:
        try:
            paths = sorted(self.folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return None
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError, TypeError):
                continue
        return None

    def list_jobs(self) -> list[dict[str, Any]]:
        try:
            paths = sorted(self.folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return []
        jobs: list[dict[str, Any]] = []
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    continue
                items = value.get("items", []) if isinstance(value.get("items"), list) else []
                entries = value.get("entries", []) if isinstance(value.get("entries"), list) else []
                jobs.append({
                    "jobId": value.get("jobId", path.stem),
                    "state": value.get("state", "unknown"),
                    "engine": value.get("engine", "capcut"),
                    "voiceId": value.get("voiceId", ""),
                    "outputDir": value.get("outputDir", ""),
                    "createdAt": value.get("createdAt", ""),
                    "completedAt": value.get("completedAt", ""),
                    "total": len(entries),
                    "completed": sum(item.get("status") == "completed" for item in items if isinstance(item, dict)),
                    "failed": sum(item.get("status") == "failed" for item in items if isinstance(item, dict)),
                })
            except (OSError, ValueError, TypeError):
                continue
        return jobs

    def get(self, job_id: str) -> dict[str, Any]:
        path = self.path(job_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("Không tìm thấy job đã chọn") from exc
        if not isinstance(value, dict):
            raise ValueError("Dữ liệu job không hợp lệ")
        return value

    def register(self, job_id: str, control_path: Path | None = None) -> dict[str, Any]:
        job_id = self.validate_job_id(job_id)
        control: dict[str, Any] = {"pause": threading.Event(), "cancel": threading.Event()}
        if control_path is not None:
            control["controlPath"] = control_path
        with self._lock:
            if job_id in self._controls:
                raise ValueError("Job ID đang được sử dụng bởi tác vụ khác")
            self._controls[job_id] = control
        return control

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._controls.pop(job_id, None)

    def control(self, job_id: str, action: str) -> dict[str, str]:
        self.validate_job_id(job_id)
        with self._lock:
            control = self._controls.get(job_id)
        if not control:
            raise ValueError("Job không còn chạy; hãy tiếp tục job để xử lý phần còn lại")
        if action == "pause":
            control["pause"].set()
            state = "paused"
        elif action == "resume":
            control["pause"].clear()
            state = "running"
        elif action == "cancel":
            control["cancel"].set()
            control["pause"].clear()
            state = "cancelled"
        else:
            raise ValueError("Lệnh điều khiển job không hợp lệ")
        control_path = control.get("controlPath")
        if isinstance(control_path, Path):
            self._atomic_json(control_path, {"state": state})
        event = {"jobId": job_id, "state": state}
        self.emit({"event": "srt.voice.job", "data": event})
        return event

    def _prune(self) -> None:
        try:
            paths = sorted(self.folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return
        with self._lock:
            active = set(self._controls)
        retained = 0
        for path in paths:
            if path.stem in active or retained < self.retention:
                retained += 1
                continue
            try:
                path.unlink()
            except OSError:
                pass
