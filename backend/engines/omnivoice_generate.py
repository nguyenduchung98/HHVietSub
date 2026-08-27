from __future__ import annotations

import argparse
import json
from pathlib import Path


def send(stage: str, message: str) -> None:
    print(json.dumps({"event": "progress", "stage": stage, "message": message}, ensure_ascii=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", default="vi")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--guidance", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--denoise", action="store_true")
    parser.add_argument("--postprocess", action="store_true")
    args = parser.parse_args()

    send("startup", "Đang khởi động Python OmniVoice…")
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice, VoiceClonePrompt
    send("runtime", "Đã nạp PyTorch; đang chuẩn bị model…")

    profile_path = args.voice_dir / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    audio_path = args.voice_dir / str(profile["ref_audio"])
    text_path = args.voice_dir / str(profile.get("ref_text_file", "ref_text.txt"))
    ref_text = text_path.read_text(encoding="utf-8").strip() if text_path.exists() else None
    prompt_path = args.voice_dir / str(profile.get("voice_prompt", "voice.pt"))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    dtype = torch.float16 if device == "cuda" else torch.float32
    send("model", f"Đang nạp OmniVoice 0.2.1 trên {device.upper()}…")
    model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device, dtype=dtype, load_asr=not bool(ref_text))
    send("model_ready", "Model đã sẵn sàng; đang nạp hồ sơ giọng…")
    generate_args = dict(text=args.text, language=args.language or None, speed=args.speed,
                         num_step=args.steps, guidance_scale=args.guidance,
                         denoise=args.denoise, postprocess_output=args.postprocess)
    if prompt_path.exists():
        try:
            generate_args["voice_clone_prompt"] = VoiceClonePrompt.load(str(prompt_path))
        except (AttributeError, KeyError, TypeError, ValueError):
            data = torch.load(prompt_path, map_location="cpu", weights_only=True)
            generate_args["voice_clone_prompt"] = VoiceClonePrompt(
                ref_audio_tokens=data["ref_audio_tokens"], ref_text=data["ref_text"], ref_rms=data["ref_rms"])
    else:
        generate_args.update(ref_audio=str(audio_path), ref_text=ref_text)
    send("generating", "Đang tạo audio…")
    with torch.inference_mode():
        audio = model.generate(**generate_args)[0]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, audio, model.sampling_rate)
    send("complete", "Đã tạo audio thành công.")
    print(json.dumps({"output": str(args.output), "sample_rate": model.sampling_rate}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
