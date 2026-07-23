from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


def send(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), flush=True)


def control_state(path: Path | None) -> str:
    if path is None:
        return "running"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("state", "running"))
    except (OSError, ValueError, TypeError):
        return "running"


def wait_for_control(path: Path | None) -> bool:
    while control_state(path) == "paused":
        time.sleep(0.25)
    return control_state(path) != "cancelled"


def apply_speed(path: Path, speed: float) -> None:
    if abs(speed - 1.0) < 0.01:
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        send({"event": "warning", "message": "FFmpeg not found; keeping natural speed"})
        return
    temporary = path.with_suffix(".speed.wav")
    result = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={speed:.4f}", str(temporary)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode == 0 and temporary.is_file():
        os.replace(temporary, path)
    elif temporary.exists():
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    output_dir = Path(job["outputDir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    import soundfile as sf
    import torch
    from vieneu import Vieneu

    device = "cuda" if torch.cuda.is_available() else "cpu"
    send({"event": "model", "status": "loading", "engine": "vieneu", "device": device})
    try:
        tts = Vieneu(
            mode="v3turbo",
            backbone_repo=job["baseModel"],
            moss_tokenizer=job["codecModel"],
            device=device,
            backend="pytorch" if device == "cuda" else "onnx",
            max_batch_size=min(32, max(1, int(job.get("batchSize", 8)))),
        )
        voice_name = job.get("voice", "Ngọc Lan")
        available = {voice_id for _, voice_id in tts.list_preset_voices()}
        if voice_name not in available:
            raise RuntimeError(f"VieNeu preset '{voice_name}' không tồn tại. Có sẵn: {', '.join(sorted(available))}")
        voice = tts.get_preset_voice(voice_name)
    except Exception as exc:
        send({"event": "error", "message": f"Lỗi nạp mô hình VieNeu-TTS: {exc}"})
        raise

    entries = list(job.get("entries", []))
    batch_size = min(32, max(1, int(job.get("batchSize", 8))))
    speed = min(2.0, max(0.5, float(job.get("speed", 1.0))))
    done = completed = failed = 0
    started = time.time()
    try:
        for offset in range(0, len(entries), batch_size):
            if not wait_for_control(args.control):
                break
            batch = entries[offset:offset + batch_size]
            pending = []
            for entry in batch:
                output = output_dir / f"{int(entry['id']):04d}.wav"
                if job.get("skipExisting", True) and output.is_file() and output.stat().st_size > 44:
                    info = sf.info(str(output))
                    item = {**entry, "status": "completed", "file": str(output), "duration": round(float(info.duration), 3), "skipped": True, "engine": "vieneu"}
                    done += 1; completed += 1
                    send({"event": "progress", "done": done, "total": len(entries), "item": item})
                else:
                    pending.append((entry, output))
            if not pending:
                continue

            audios = None
            last_error = None
            for attempt in range(1, 4):
                if not wait_for_control(args.control):
                    break
                for entry, _ in pending:
                    send({"event": "attempt", "id": int(entry["id"]), "attempt": attempt, "total": len(entries)})
                try:
                    with torch.inference_mode():
                        audios = tts.infer_batch(
                            [str(entry["text"]) for entry, _ in pending], voice=voice,
                            batch_size=batch_size, temperature=0.8, apply_watermark=True,
                        )
                    if len(audios) != len(pending):
                        raise RuntimeError("Audio count does not match batch")
                    break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < 3:
                        time.sleep(attempt)

            if audios is None:
                for entry, _ in pending:
                    item = {**entry, "status": "failed", "error": last_error or "Cancelled", "attempts": 3, "engine": "vieneu"}
                    done += 1; failed += 1
                    send({"event": "progress", "done": done, "total": len(entries), "item": item})
                continue

            for (entry, output), audio in zip(pending, audios):
                temporary = output.with_suffix(".wav.tmp")
                sf.write(str(temporary), audio, tts.sample_rate, format="WAV")
                os.replace(temporary, output)
                apply_speed(output, speed)
                info = sf.info(str(output))
                item = {**entry, "status": "completed", "file": str(output), "duration": round(float(info.duration), 3), "engine": "vieneu"}
                done += 1; completed += 1
                send({"event": "progress", "done": done, "total": len(entries), "item": item})
    finally:
        close = getattr(tts, "close", None)
        if callable(close):
            close()
    state = "cancelled" if control_state(args.control) == "cancelled" else "completed"
    send({"event": "complete", "state": state, "completed": completed, "failed": failed, "elapsed": round(time.time() - started, 2)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
