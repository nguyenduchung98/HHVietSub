import json
import tempfile
import unittest
import wave
from pathlib import Path

from backend.services.voice_studio_service import VoiceStudioService, build_srt, slugify


def write_wav(path: Path, seconds: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\0\0" * int(8_000 * seconds))


class TestVoiceStudioService(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.user_data = self.root / "data"
        self.omnivoice = self.root / "omnivoice"
        self.voice_dir = self.omnivoice / "voices" / "demo"
        self.voice_dir.mkdir(parents=True)
        write_wav(self.voice_dir / "ref.wav")
        (self.voice_dir / "profile.json").write_text(json.dumps({
            "name": "Demo", "language": "vi", "ref_audio": "ref.wav", "voice_prompt": "voice.pt"
        }), encoding="utf-8")
        self.service = VoiceStudioService(
            self.user_data, self.root, self.omnivoice, lambda: {"mode": "colab"}, self.remote_generate
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def remote_generate(text, voice_id, params, output):
        write_wav(output)
        return {"duration": 0.05, "generationTime": 0.01, "seed": 1}

    def test_list_and_reference_reject_profile_path_escape(self):
        voices = self.service.list_voices()
        self.assertEqual(voices[0]["id"], "demo")
        self.assertTrue(voices[0]["ready"])
        with self.assertRaises(ValueError):
            self.service.voice_reference("../demo")
        (self.voice_dir / "profile.json").write_text(json.dumps({"ref_audio": "../outside.wav"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.voice_reference("demo")

    def test_remote_generate_creates_atomic_history_and_srt(self):
        record = self.service.generate({"text": "Hello. World!", "voiceId": "demo", "createSrt": True})
        self.assertTrue(Path(record["path"]).is_file())
        self.assertTrue(Path(record["srtPath"]).is_file())
        history = self.service.history()
        self.assertEqual(history[0]["id"], record["id"])
        self.assertEqual(len(list(self.user_data.glob("*.tmp"))), 0)
        self.assertTrue(self.service.delete_history(record["id"])["deleted"])
        self.assertEqual(self.service.history(), [])

    def test_generation_failure_removes_partial_output(self):
        def failing(text, voice_id, params, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"partial")
            raise RuntimeError("failed")

        self.service.remote_generate = failing
        with self.assertRaises(RuntimeError):
            self.service.generate({"text": "Hello", "voiceId": "demo"})
        self.assertEqual(list((self.user_data / "outputs").glob("*")), [])

    def test_helpers_handle_vietnamese_and_zero_duration(self):
        self.assertEqual(slugify("Giọng Đọc"), "giong-doc")
        self.assertIn("00:00:00,000 --> 00:00:00,000", build_srt("Xin chào", 0))


if __name__ == "__main__":
    unittest.main()
