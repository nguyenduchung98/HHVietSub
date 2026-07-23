from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice-dir", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from omnivoice.models.omnivoice import OmniVoice

    profile_path = args.voice_dir / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    audio_path = args.voice_dir / str(profile["ref_audio"])
    text_path = args.voice_dir / str(profile.get("ref_text_file", "ref_text.txt"))
    ref_text = text_path.read_text(encoding="utf-8").strip() if text_path.is_file() else ""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = OmniVoice.from_pretrained(
        str(profile.get("model") or "k2-fsa/OmniVoice"),
        device_map=device,
        dtype=dtype,
        load_asr=not bool(ref_text),
    )
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(audio_path),
        ref_text=ref_text or None,
        preprocess_prompt=bool(profile.get("preprocess_prompt", False)),
    )
    prompt_path = args.voice_dir / str(profile.get("voice_prompt", "voice.pt"))
    temporary = prompt_path.with_suffix(".pt.tmp")
    torch.save({
        "ref_audio_tokens": prompt.ref_audio_tokens.cpu(),
        "ref_text": prompt.ref_text,
        "ref_rms": prompt.ref_rms,
    }, temporary)
    temporary.replace(prompt_path)
    if not ref_text and prompt.ref_text:
        text_path.write_text(str(prompt.ref_text), encoding="utf-8")
        profile["auto_transcribe"] = True
    profile["voice_prompt"] = prompt_path.name
    profile["prompt_created_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"voicePrompt": str(prompt_path), "device": device}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
