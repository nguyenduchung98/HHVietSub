from __future__ import annotations

import json
import sys
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
    send({"event": "runtime", "stage": "startup", "message": "Đang khởi động Python OmniVoice…"})
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice, VoiceClonePrompt

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = None
    prompt_cache: dict[str, tuple[int, object]] = {}
    send({"event": "runtime", "stage": "ready", "device": device,
          "message": f"Runtime OmniVoice 0.2.1 sẵn sàng trên {device.upper()}."})

    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            request_id = str(request.get("id", ""))
            action = str(request.get("action", ""))
            if action == "shutdown":
                send({"id": request_id, "ok": True})
                return 0
            if action != "generate":
                raise ValueError(f"Unsupported action: {action}")

            started = time.perf_counter()
            if model is None:
                send({"event": "progress", "id": request_id, "stage": "model",
                      "message": f"Đang nạp OmniVoice 0.2.1 trên {device.upper()}…"})
                model = OmniVoice.from_pretrained(
                    str(request.get("model") or "k2-fsa/OmniVoice"),
                    device_map=device, dtype=dtype, load_asr=False,
                )
                send({"event": "progress", "id": request_id, "stage": "model_ready",
                      "message": "Model đã được giữ trong bộ nhớ; đang nạp hồ sơ giọng…"})

            voice_dir = Path(str(request["voiceDir"]))
            profile = json.loads((voice_dir / "profile.json").read_text(encoding="utf-8"))
            prompt_path = voice_dir / str(profile.get("voice_prompt", "voice.pt"))
            cache_key = str(prompt_path.resolve())
            prompt_mtime = prompt_path.stat().st_mtime_ns if prompt_path.is_file() else 0
            cached = prompt_cache.get(cache_key)
            if cached and cached[0] == prompt_mtime:
                prompt = cached[1]
            elif prompt_path.is_file():
                prompt = load_prompt(prompt_path, VoiceClonePrompt, torch)
                prompt_cache[cache_key] = (prompt_mtime, prompt)
            else:
                audio_path = voice_dir / str(profile["ref_audio"])
                text_path = voice_dir / str(profile.get("ref_text_file", "ref_text.txt"))
                ref_text = text_path.read_text(encoding="utf-8").strip() if text_path.is_file() else None
                prompt = model.create_voice_clone_prompt(ref_audio=str(audio_path), ref_text=ref_text)

            seed = int(request.get("seed") or 0)
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            send({"event": "progress", "id": request_id, "stage": "generating",
                  "message": "Đang tạo audio…"})
            with torch.inference_mode():
                audio = model.generate(
                    text=str(request["text"]),
                    language=str(request.get("language") or "vi") or None,
                    voice_clone_prompt=prompt,
                    speed=float(request.get("speed", 1.0)),
                    num_step=int(request.get("steps", 32)),
                    guidance_scale=float(request.get("guidance", 2.0)),
                    denoise=bool(request.get("denoise", False)),
                    postprocess_output=bool(request.get("postprocess", True)),
                )[0]
            output = Path(str(request["output"]))
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(".wav.tmp")
            sf.write(str(temporary), audio, model.sampling_rate, format="WAV")
            temporary.replace(output)
            send({"event": "progress", "id": request_id, "stage": "complete",
                  "message": "Đã tạo audio thành công."})
            send({"id": request_id, "ok": True, "sampleRate": model.sampling_rate,
                  "generationTime": round(time.perf_counter() - started, 2)})
        except Exception as exc:
            send({"id": locals().get("request_id", ""), "ok": False,
                  "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
