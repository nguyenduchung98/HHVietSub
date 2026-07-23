from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def send(payload: dict) -> None:
    # Keep progress events safe on Windows consoles that still default to cp1252.
    print(json.dumps(payload, ensure_ascii=True), flush=True)


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
    from omnivoice.models.omnivoice import OmniVoice, VoiceClonePrompt

    profile = json.loads((voice_dir / "profile.json").read_text(encoding="utf-8"))
    text_path = voice_dir / str(profile.get("ref_text_file", "ref_text.txt"))
    ref_text = text_path.read_text(encoding="utf-8").strip() if text_path.exists() else None
    prompt_path = voice_dir / str(profile.get("voice_prompt", "voice.pt"))
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    send({"event": "model", "status": "loading", "device": device, "message": f"Đang nạp OmniVoice trên {device.upper()}…"})
    model_path = Path(str(job.get("modelPath", ""))).resolve()
    if not (model_path / "config.json").is_file():
        raise RuntimeError(f"OmniVoice snapshot không hợp lệ: {model_path}")
    send({"event": "model", "status": "loading", "device": device,
          "message": f"Đang nạp OmniVoice local từ {model_path.name} trên {device.upper()}…"})
    model = OmniVoice.from_pretrained(
        str(model_path), device_map=device, dtype=dtype,
        load_asr=not bool(ref_text), local_files_only=True,
    )
    prompt = None
    if prompt_path.exists():
        # OmniVoice >= 0.2.1 provides the canonical cross-session loader.
        # Keep compatibility with the Vietnamese profiles created by speak.py
        # on OmniVoice 0.1.x, which store the same fields as a plain dict.
        if hasattr(VoiceClonePrompt, "load"):
            prompt = VoiceClonePrompt.load(prompt_path)
        else:
            data = torch.load(prompt_path, map_location="cpu", weights_only=True)
            prompt = VoiceClonePrompt(
                ref_audio_tokens=data["ref_audio_tokens"],
                ref_text=data["ref_text"],
                ref_rms=data["ref_rms"],
            )
    else:
        send({"event": "prompt", "status": "building", "message": "Đang tạo voice.pt từ audio tham chiếu…"})
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(voice_dir / str(profile["ref_audio"])),
            ref_text=ref_text,
            preprocess_prompt=bool(profile.get("preprocess_prompt", False)),
        )
        temporary_prompt = prompt_path.with_suffix(".pt.tmp")
        if hasattr(prompt, "save"):
            prompt.save(temporary_prompt)
        else:
            torch.save({
                "ref_audio_tokens": prompt.ref_audio_tokens.cpu(),
                "ref_text": prompt.ref_text,
                "ref_rms": prompt.ref_rms,
            }, temporary_prompt)
        temporary_prompt.replace(prompt_path)
        send({"event": "prompt", "status": "ready", "message": "Đã tạo voice.pt; bắt đầu tạo phụ đề…"})
    send({"event": "model", "status": "ready", "device": device, "message": "Model đã sẵn sàng; bắt đầu tạo câu 0001…"})

    entries = job["entries"]
    completed = []
    failed = []
    started = time.time()
    for position, entry in enumerate(entries, 1):
        item_id = int(entry["id"])
        filename = f"{item_id:04d}.wav"
        output_path = output_dir / filename
        if job.get("skipExisting") and output_path.exists() and output_path.stat().st_size > 44:
            info = sf.info(str(output_path))
            result = {**entry, "file": str(output_path), "duration": round(float(info.duration), 3), "status": "completed", "skipped": True}
            completed.append(result)
            send({"event": "progress", "done": position, "total": len(entries), "item": result})
            continue
        last_error = ""
        success = None
        for attempt in range(1, 4):
            try:
                send({"event": "attempt", "done": position - 1, "total": len(entries), "id": item_id, "attempt": attempt})
                seed = int(job.get("seed") or int(time.time_ns() % 2_147_483_647)) + item_id + attempt - 1
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
                generate_args = dict(
                    text=str(entry["text"]), language=job.get("language") or None,
                    speed=float(job.get("speed", 1.0)), num_step=int(job.get("steps", 32)),
                    guidance_scale=float(job.get("guidance", 2.0)), denoise=bool(job.get("denoise", False)),
                    postprocess_output=bool(job.get("postprocess", True)),
                )
                generate_args["voice_clone_prompt"] = prompt
                with torch.inference_mode():
                    audio = model.generate(**generate_args)[0]
                temporary = output_path.with_suffix(".wav.tmp")
                sf.write(str(temporary), audio, model.sampling_rate, format="WAV")
                info = sf.info(str(temporary))
                if info.frames <= 0:
                    raise RuntimeError("Audio rỗng")
                os.replace(temporary, output_path)
                success = {**entry, "file": str(output_path), "duration": round(float(info.duration), 3), "status": "completed", "attempts": attempt, "seed": seed}
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        if success:
            completed.append(success)
            item = success
        else:
            item = {**entry, "status": "failed", "error": last_error, "attempts": 3}
            failed.append(item)
        send({"event": "progress", "done": position, "total": len(entries), "item": item})

    send({"event": "complete", "completed": len(completed), "failed": len(failed), "elapsed": round(time.time() - started, 2)})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        send({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
        raise
