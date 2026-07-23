from __future__ import annotations

import re
from pathlib import Path
from typing import Any


TIMESTAMP_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)


def _timestamp_value(parts: tuple[str, ...]) -> int:
    hour, minute, second, millis = (int(part) for part in parts)
    if minute > 59 or second > 59:
        raise ValueError("Timestamp SRT có phút hoặc giây không hợp lệ")
    return ((hour * 60 + minute) * 60 + second) * 1000 + millis


def normalize_timing(value: str) -> tuple[str, str]:
    match = TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("Timestamp SRT không hợp lệ")
    groups = match.groups()
    start_value = _timestamp_value(groups[:4])
    end_value = _timestamp_value(groups[4:])
    if end_value < start_value:
        raise ValueError("Thời gian kết thúc phụ đề nhỏ hơn thời gian bắt đầu")
    start = f"{groups[0]}:{groups[1]}:{groups[2]},{groups[3]}"
    end = f"{groups[4]}:{groups[5]}:{groups[6]},{groups[7]}"
    return start, end


class SubtitleService:
    MAX_FILE_BYTES = 20 * 1024 * 1024

    @classmethod
    def parse(cls, file_path: Path) -> dict[str, Any]:
        path = file_path.resolve()
        if path.suffix.lower() != ".srt" or not path.is_file():
            raise ValueError("Vui lòng chọn một file SRT hợp lệ")
        if path.stat().st_size > cls.MAX_FILE_BYTES:
            raise ValueError("File SRT vượt quá giới hạn 20 MB")
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = re.split(r"\r?\n\s*\r?\n", content.strip())
        entries: list[dict[str, Any]] = []
        warnings: list[str] = []
        used_ids: set[int] = set()
        for position, block in enumerate(blocks, 1):
            lines = [line.rstrip() for line in block.splitlines()]
            if len(lines) < 2:
                warnings.append(f"Khối {position} không đủ dữ liệu")
                continue
            try:
                entry_id = int(lines[0].strip())
                timing_line, text_lines = lines[1].strip(), lines[2:]
            except ValueError:
                entry_id = position
                timing_line, text_lines = lines[0].strip(), lines[1:]
            try:
                start, end = normalize_timing(timing_line)
            except ValueError as exc:
                warnings.append(f"Khối {position}: {exc}")
                continue
            if entry_id <= 0 or entry_id in used_ids:
                warnings.append(f"Khối {position} có ID trùng hoặc không hợp lệ; đã đánh lại ID")
                entry_id = position
                while entry_id in used_ids:
                    entry_id += 1
            used_ids.add(entry_id)
            text = "\n".join(text_lines).strip()
            if not text:
                warnings.append(f"Khối {position} không có nội dung")
            entries.append({"id": entry_id, "start": start, "end": end, "source": text, "translated": ""})
        if not entries:
            raise ValueError("Không đọc được câu phụ đề nào trong file")
        return {
            "path": str(path), "name": path.name, "entries": entries, "warnings": warnings,
            "characters": sum(len(item["source"]) for item in entries),
        }

    @staticmethod
    def save(source_path: Path, entries: Any, output_value: str = "") -> dict[str, Any]:
        source = source_path.resolve()
        if source.suffix.lower() != ".srt" or not source.is_file():
            raise ValueError("File SRT nguồn không hợp lệ")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Không có dữ liệu phụ đề để lưu")
        output = Path(output_value).resolve() if output_value.strip() else source.with_name(f"{source.stem}_vi.srt")
        if output.suffix.lower() != ".srt" or output.parent != source.parent:
            raise ValueError("File kết quả phải là SRT và nằm cùng thư mục file nguồn")
        blocks = []
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                continue
            start, end = normalize_timing(f"{entry.get('start', '')} --> {entry.get('end', '')}")
            text = str(entry.get("translated") or entry.get("source") or "").strip()
            if not text:
                continue
            blocks.append(f"{index}\n{start} --> {end}\n{text}")
        if not blocks:
            raise ValueError("Không có câu phụ đề hợp lệ để lưu")
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        temporary.replace(output)
        return {"path": str(output), "entries": len(blocks)}
