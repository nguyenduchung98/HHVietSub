import tempfile
import threading
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from backend.services.settings_service import SettingsService
from backend.services.tts_api_service import TtsApiService


class TestTtsApiService(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.settings = SettingsService(Path(self.temporary.name))
        self.settings.set_secrets({"ai33Key": "key-one\nkey-two", "aimaxKey": "aimax-key"})
        self.service = TtsApiService(self.settings)

    def tearDown(self):
        self.temporary.cleanup()

    def test_voice_records_support_nested_provider_payloads(self):
        payload = {"data": {"results": [{"voice_id": "voice-1"}]}}
        self.assertEqual(self.service.voice_records(payload)[0]["voice_id"], "voice-1")
        self.assertEqual(self.service.voice_records({"data": "invalid"}), [])

    def test_cancelled_request_never_opens_network(self):
        cancel = threading.Event()
        cancel.set()
        with patch("backend.services.tts_api_service.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(RuntimeError, "hủy"):
                self.service.request_json("https://api.ai33.pro/test", {}, control={"cancel": cancel})
        urlopen.assert_not_called()

    def test_ai33_voice_mapping_deduplicates_ids(self):
        response = {"voices": [
            {"voice_id": "v1", "name": "Voice One", "preview_url": "https://cdn.example/v1.mp3"},
            {"voice_id": "v1", "name": "Duplicate"},
        ]}
        with patch.object(self.service, "request_json", return_value=response):
            result = self.service.list_voices("ai33", "edge", "vi")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["voices"][0]["name"], "Voice One")

    def test_capcut_direct_voice_mapping_needs_no_api_key(self):
        result = self.service.list_voices("capcut", language="Vietnamese")
        self.assertGreaterEqual(result["total"], 1)
        self.assertTrue(any(
            voice["id"] == "BV074_streaming::7102355709945188865"
            for voice in result["voices"]
        ))
        self.assertEqual(result["provider"], "capcut-direct")

    def test_capcut_direct_generates_mp3_without_conversion(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self): return b"ID3" + b"\0" * 256

        destination = Path(self.temporary.name) / "0001.mp3"
        with patch("backend.services.tts_api_service.capcut_synthesize", return_value="https://cdn.example/audio.mp3") as request, \
             patch("backend.services.tts_api_service.urllib.request.urlopen", return_value=Response()):
            result = self.service.generate_one(
                "capcut", {"id": 1, "text": "Xin chào"},
                {"apiVoiceId": "BV074_streaming::7102355709945188865", "speed": 1.1},
                destination,
            )
        self.assertEqual(result["format"], "mp3")
        self.assertTrue(destination.is_file())
        self.assertEqual(request.call_args.args[1], "BV074_streaming")
        self.assertEqual(request.call_args.args[2], "7102355709945188865")

    def test_generate_one_rotates_keys_by_entry_id(self):
        calls = []

        def request_json(url, headers, method="GET", fields=None, timeout=60, control=None):
            calls.append((url, headers, method, fields))
            if url.endswith("/text-to-speech"):
                return {"task_id": "job-1"}
            return {"status": "completed", "audio_url": "/audio.wav"}

        with patch.object(self.service, "request_json", side_effect=request_json), \
             patch.object(self.service, "download_audio", return_value=1.25):
            result = self.service.generate_one(
                "ai33", {"id": 2, "text": "Xin chào"}, {"apiVoiceId": "voice-1", "speed": 1},
                Path(self.temporary.name) / "0002.wav",
            )
        self.assertEqual(calls[0][1]["xi-api-key"], "key-two")
        self.assertEqual(result["duration"], 1.25)

    def test_unknown_provider_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            self.service.test_keys("unknown", "secret")


if __name__ == "__main__":
    unittest.main()
