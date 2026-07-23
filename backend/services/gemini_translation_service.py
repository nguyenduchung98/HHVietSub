from __future__ import annotations

import json
import logging
import queue
import re
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


MODEL_RE = re.compile(r"^gemini-[a-zA-Z0-9._-]+$")


class GeminiTranslationService:
    _browser_lock = threading.Lock()

    def __init__(self, legacy_root: Path):
        self.legacy_root = legacy_root

    @staticmethod
    def _input_rows(entries: Any, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(entries, list) or not entries or (limit is not None and len(entries) > limit):
            suffix = f" từ 1 đến {limit} câu" if limit else ""
            raise ValueError(f"Danh sách phụ đề phải có{suffix}")
        rows = []
        used: set[int] = set()
        for index, item in enumerate(entries, 1):
            if not isinstance(item, dict):
                continue
            item_id = int(item.get("id", index))
            text = str(item.get("text", "")).strip()
            if item_id in used or not text:
                raise ValueError("ID phụ đề bị trùng hoặc nội dung dịch bị rỗng")
            used.add(item_id)
            rows.append({"id": item_id, "text": text})
        if not rows:
            raise ValueError("Không có câu phụ đề hợp lệ để dịch")
        return rows

    def translate_api(self, params: dict[str, Any]) -> dict[str, Any]:
        api_key = str(params.get("apiKey", "")).strip()
        model = str(params.get("model", "gemini-3.5-flash")).strip()
        if not api_key:
            raise ValueError("Vui lòng nhập Gemini API key")
        if not MODEL_RE.fullmatch(model):
            raise ValueError("Tên model Gemini không hợp lệ")
        rows = self._input_rows(params.get("entries"), 40)
        source_language = str(params.get("sourceLanguage", "Auto")).strip()
        target_language = str(params.get("targetLanguage", "Tiếng Việt")).strip()
        glossary = str(params.get("glossary", "")).strip()
        prompt = (
            f"Bạn là biên dịch viên phụ đề chuyên nghiệp. Dịch từ {source_language} sang {target_language}. "
            "Giữ nguyên ý nghĩa, tên riêng, con số và ký hiệu định dạng. Viết tự nhiên, súc tích để đọc trên màn hình. "
            "Không thêm giải thích. Trả đúng một bản dịch cho mỗi id và giữ nguyên id."
        )
        if glossary:
            prompt += f"\nThuật ngữ bắt buộc áp dụng:\n{glossary}"
        prompt += "\nDữ liệu cần dịch:\n" + json.dumps(rows, ensure_ascii=False)
        schema = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "id": {"type": "INTEGER"}, "translated": {"type": "STRING"}}, "required": ["id", "translated"]}}
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {
            "temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema}}
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("error", {}).get("message", detail)
            except ValueError:
                message = detail
            raise RuntimeError(f"Gemini API: {str(message)[:600]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Không kết nối được Gemini API: {exc.reason}") from exc
        try:
            raw = payload["candidates"][0]["content"]["parts"][0]["text"]
            translated = json.loads(raw)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Gemini trả về dữ liệu không đúng định dạng") from exc
        expected = {item["id"] for item in rows}
        results = {}
        for item in translated if isinstance(translated, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                item_id = int(item.get("id", -1))
            except (TypeError, ValueError):
                continue
            text = str(item.get("translated", "")).strip()
            if item_id in expected and text:
                results[item_id] = text
        rendered = [{"id": item_id, "translated": results[item_id]} for item_id in sorted(results)]
        return {"results": rendered, "requested": len(rows), "translated": len(rendered),
                "missing": sorted(expected - set(results))}

    def translate_browser(self, params: dict[str, Any]) -> dict[str, Any]:
        rows = self._input_rows(params.get("entries"))
        if not self.legacy_root.is_dir():
            raise RuntimeError("Không tìm thấy legacy Gemini browser translator")
        with self._browser_lock:
            return self._translate_browser_locked(params, rows)

    def _translate_browser_locked(self, params: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        if str(self.legacy_root) not in sys.path:
            sys.path.insert(0, str(self.legacy_root))
        import services.translator_service as translator_service  # type: ignore
        from services.translator_service import (  # type: ignore
            BrowserConfig, DEFAULT_INSTRUCTION, SeleniumGeminiTranslator,
            chunk_entries, translate_chunk_with_retries,
        )
        config_path = self.legacy_root / "config.json"
        try:
            old_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        except (OSError, ValueError, TypeError):
            old_config = {}
        gem_url = str(params.get("gemUrl") or old_config.get("endpoint") or "").strip()
        if not gem_url.startswith("https://gemini.google.com/"):
            raise ValueError("Link Gem không hợp lệ")
        batch_size = max(1, min(300, int(params.get("batchSize", old_config.get("batch", 200)))))
        workers = max(1, min(5, int(params.get("workers", old_config.get("workers", 1)))))
        profile_value = Path(str(old_config.get("chrome_profile", "../chrome_profile")))
        profile_path = profile_value if profile_value.is_absolute() else (self.legacy_root / profile_value).resolve()
        config = BrowserConfig(
            gem_url=gem_url, workers=workers,
            model_name=str(params.get("modelName") or old_config.get("model") or "").strip(),
            user_data_dir=str(profile_path), profile_directory=str(old_config.get("profile_dir", "Default")),
        )
        source_language = str(params.get("sourceLanguage", "Auto"))
        target_language = str(params.get("targetLanguage", "Tiếng Việt"))
        glossary = str(params.get("glossary", "")).strip()
        instruction = f"Dịch từ {source_language} sang {target_language}.\n" + DEFAULT_INSTRUCTION
        if glossary:
            instruction += "\nThuật ngữ bổ sung bắt buộc:\n" + glossary
        source_entries = [{"id": item["id"], "source": item["text"]} for item in rows]
        original_builder = translator_service.build_chunk_text
        translator_service.build_chunk_text = lambda chunk, rule=instruction: rule + "\n\n" + original_builder(chunk, rule)
        chunks = chunk_entries(source_entries, batch_size)
        results: dict[int, str] = {}
        translator = None
        try:
            translator = SeleniumGeminiTranslator(config=config, logger=lambda message: logging.info("Gemini: %s", message))
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
                        results.update(translate_chunk_with_retries(
                            translator=translator, chunk=chunk, instruction=instruction, tab_index=tab_index,
                            max_retries=3, logger=lambda message: logging.info("Gemini: %s", message),
                        ))
                    finally:
                        tasks.task_done()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for future in [executor.submit(run_tab, index) for index in range(workers)]:
                    future.result()
        finally:
            translator_service.build_chunk_text = original_builder
            if translator is not None:
                try:
                    translator.close()
                except Exception:
                    logging.exception("Cannot close legacy Gemini translator")
        return {"results": [{"id": item_id, "translated": text} for item_id, text in sorted(results.items())],
                "requested": len(source_entries), "translated": len(results), "chunks": len(chunks)}
