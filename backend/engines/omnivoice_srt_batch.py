from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def send(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


def load_prompt(path: Path, prompt_type, torch):
    try:
        return prompt_type.load(str(path))
    except (AttributeError, KeyError, TypeError, ValueError):
        data = torch.load(path, map_location="cpu", weights_only=True)
        return prompt_type(
            ref_audio_tokens=data["ref_audio_tokens"],
            ref_text=data["ref_text"],
            ref_rms=data["ref_rms"],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    voice_dir = Path(job["voiceDir"])
    output_dir = Path(job["outputDir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    send({"event": "startup", "status": "importing", "message": "Đang khởi động PyTorch…"})
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice, VoiceClonePrompt

    profile = json.loads((voice_dir / "profile.json").read_text(encoding="utf-8"))
    text_path = voice_dir / str(profile.get("ref_text_file", "ref_text.txt"))
    ref_text = text_path.read_text(encoding="utf-8").strip() if text_path.is_file() else None
    prompt_path = voice_dir / str(profile.get("voice_prompt", "voice.pt"))
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    model_path = Path(str(job.get("modelPath", ""))).resolve()
    if not (model_path / "config.json").is_file():
        raise RuntimeError(f"OmniVoice snapshot không hợp lệ: {model_path}")
    send({"event": "model", "status": "loading", "device": device,
          "message": f"Đang nạp OmniVoice 0.2.1 trên {device.upper()}…"})
    model = OmniVoice.from_pretrained(
        str(model_path), device_map=device, dtype=dtype,
        load_asr=not bool(ref_text), local_files_only=True,
    )

    if prompt_path.is_file():
        prompt = load_prompt(prompt_path, VoiceClonePrompt, torch)
    else:
        send({"event": "prompt", "status": "building", "message": "Đang tạo voice.pt từ audio tham chiếu…"})
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(voice_dir / str(profile["ref_audio"])),
            ref_text=ref_text,
            preprocess_prompt=bool(profile.get("preprocess_prompt", False)),
        )
        temporary_prompt = prompt_path.with_suffix(".pt.tmp")
        prompt.save(str(temporary_prompt))
        temporary_prompt.replace(prompt_path)
    send({"event": "model", "status": "ready", "device": device,
          "message": "Model đã sẵn sàng; bắt đầu batch phụ đề…"})

    entries = list(job["entries"])
    completed: list[dict] = []
    failed: list[dict] = []
    pending: list[dict] = []
    started = time.time()
    done = 0
    for entry in entries:
        item_id = int(entry["id"])
        output_path = output_dir / f"{item_id:04d}.wav"
        if job.get("skipExisting") and output_path.is_file() and output_path.stat().st_size > 44:
            info = sf.info(str(output_path))
            result = {**entry, "file": str(output_path), "duration": round(float(info.duration), 3),
                      "status": "completed", "skipped": True}
            completed.append(result)
            done += 1
            send({"event": "progress", "done": done, "total": len(entries), "item": result})
        else:
            pending.append(entry)

    batch_size = max(1, min(16, int(job.get("batchSize", 4))))

    def generate_group(group: list[dict], attempt: int) -> list[dict]:
        seed = int(job.get("seed") or int(time.time_ns() % 2_147_483_647)) + int(group[0]["id"]) + attempt - 1
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        send({"event": "batch", "done": done, "total": len(entries), "batchSize": len(group),
              "first": int(group[0]["id"]), "last": int(group[-1]["id"]), "attempt": attempt})
        with torch.inference_mode():
            audios = model.generate(
                text=[str(item["text"]) for item in group],
                language=[job.get("language") or None] * len(group),
                voice_clone_prompt=[prompt] * len(group),
                speed=[float(job.get("speed", 1.0))] * len(group),
                num_step=int(job.get("steps", 32)),
                guidance_scale=float(job.get("guidance", 2.0)),
                denoise=bool(job.get("denoise", False)),
                postprocess_output=bool(job.get("postprocess", True)),
            )
        results = []
        for entry, audio in zip(group, audios):
            item_id = int(entry["id"])
            output_path = output_dir / f"{item_id:04d}.wav"
            temporary = output_path.with_suffix(".wav.tmp")
            sf.write(str(temporary), audio, model.sampling_rate, format="WAV")
            info = sf.info(str(temporary))
            if info.frames <= 0:
                raise RuntimeError(f"Audio rỗng ở câu {item_id}")
            os.replace(temporary, output_path)
            results.append({**entry, "file": str(output_path), "duration": round(float(info.duration), 3),
                            "status": "completed", "attempts": attempt, "seed": seed})
        return results

    for offset in range(0, len(pending), batch_size):
        group = pending[offset:offset + batch_size]
        group_results = None
        last_error = ""
        for attempt in range(1, 4):
            try:
                group_results = generate_group(group, attempt)
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        if group_results is None and len(group) > 1:
            send({"event": "warning", "message": "Batch lỗi; chuyển sang tạo từng câu an toàn."})
            group_results = []
            for entry in group:
                try:
                    group_results.extend(generate_group([entry], 1))
                except Exception as exc:
                    item = {**entry, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "attempts": 1}
                    failed.append(item)
                    done += 1
                    send({"event": "progress", "done": done, "total": len(entries), "item": item})
        elif group_results is None:
            item = {**group[0], "status": "failed", "error": last_error, "attempts": 3}
            failed.append(item)
            done += 1
            send({"event": "progress", "done": done, "total": len(entries), "item": item})
            continue

        for item in group_results or []:
            completed.append(item)
            done += 1
            send({"event": "progress", "done": done, "total": len(entries), "item": item})

    send({"event": "complete", "completed": len(completed), "failed": len(failed),
          "elapsed": round(time.time() - started, 2)})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        send({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
        raise
