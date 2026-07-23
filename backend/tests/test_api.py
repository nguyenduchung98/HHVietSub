import unittest
import sys
import json
import io
import wave
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.worker.main import Worker


class MockResponse:
    def __init__(self, data):
        self.data = data
    def read(self):
        return self.data
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestSecretMigration(unittest.TestCase):
    def test_plaintext_secrets_are_exported_then_scrubbed(self):
        with tempfile.TemporaryDirectory() as folder:
            user_data = Path(folder)
            (user_data / "voice-backend.json").write_text(json.dumps({
                "mode": "colab", "url": "https://example.test", "token": "legacy-token"
            }), encoding="utf-8")
            (user_data / "tts-api-settings.json").write_text(json.dumps({
                "ai33Key": "key-one\nkey-two", "aimaxKey": "key-three"
            }), encoding="utf-8")
            worker = Worker(user_data)

            exported = worker.secrets_export({})
            self.assertEqual(exported["voiceToken"], "legacy-token")
            self.assertEqual(exported["ai33Key"], "key-one\nkey-two")
            worker.secrets_set(exported)

            voice_file = json.loads((user_data / "voice-backend.json").read_text(encoding="utf-8"))
            tts_file = json.loads((user_data / "tts-api-settings.json").read_text(encoding="utf-8"))
            self.assertNotIn("token", voice_file)
            self.assertEqual(tts_file, {})
            self.assertEqual(worker.settings_get({})["voiceBackend"]["token"], "")
            self.assertNotIn("key-one", json.dumps(worker.tts_settings_get({})))
            self.assertEqual(worker.tts_settings_get({})["ai33KeyCount"], 2)


class TestWorkerExternalApis(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user_data = Path(self.temp_dir.name)
        self.worker = Worker(self.user_data)
        
        # Load mock API keys into the worker's in-memory secret store.
        self.worker.secrets_set({"ai33Key": "mock-ai33-key", "aimaxKey": "mock-aimax-key"})
        
        # Build a valid 1-second WAV file in memory to mock audio downloads
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b'\x00' * 48000)  # 24000 frames * 2 bytes/frame = 1s of silence
        self.mock_wav_bytes = wav_buffer.getvalue()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch('backend.worker.main.emit')
    def test_parallel_api_requests_are_started_at_configured_intervals(self, _mock_emit):
        starts = []

        def generate(_engine, entry, _params, output, _control):
            starts.append(time.monotonic())
            return {**entry, "status": "completed", "file": str(output), "duration": 1.0}

        params = {
            "outputDir": str(self.user_data / "staggered_output"),
            "apiWorkers": 3,
            "apiRequestInterval": 0.04,
            "jobId": "job-stagger-test",
        }
        entries = [{"id": index, "text": f"Line {index}"} for index in range(1, 4)]

        with patch.object(self.worker, '_api_generate_one', side_effect=generate):
            result = self.worker._srt_api_generate("ai33", params, entries)

        self.assertEqual(result["completed"], 3)
        ordered = sorted(starts)
        self.assertEqual(len(ordered), 3)
        self.assertGreaterEqual(ordered[1] - ordered[0], 0.03)
        self.assertGreaterEqual(ordered[2] - ordered[1], 0.03)

    @patch('urllib.request.urlopen')
    def test_tts_settings_test_ai33(self, mock_urlopen):
        # Setup mock URL handlers
        def side_effect(request, **kwargs):
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            if "api.ai33.pro/v3/voices" in url:
                return MockResponse(json.dumps({"voices": [{"id": "test-voice"}]}).encode("utf-8"))
            raise ValueError(f"Unexpected URL request: {url}")
        
        mock_urlopen.side_effect = side_effect
        result = self.worker.tts_settings_test({"provider": "ai33", "key": "new-mock-key"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "ai33")

    @patch('urllib.request.urlopen')
    def test_tts_settings_test_aimax(self, mock_urlopen):
        def side_effect(request, **kwargs):
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            if "aimaxstudio.com/api/v1/voices" in url:
                return MockResponse(json.dumps({"voices": [{"id": "test-voice"}]}).encode("utf-8"))
            raise ValueError(f"Unexpected URL request: {url}")
        
        mock_urlopen.side_effect = side_effect
        result = self.worker.tts_settings_test({"provider": "aimax", "key": "new-mock-key"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "aimax")

    @patch('urllib.request.urlopen')
    @patch('backend.worker.main.emit')
    def test_srt_api_generate_ai33(self, mock_emit, mock_urlopen):
        def side_effect(request, **kwargs):
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            # 1. Generate task request
            if "api.ai33.pro/v3/text-to-speech" in url:
                return MockResponse(json.dumps({"task_id": "task-123"}).encode("utf-8"))
            # 2. Status check request
            if "api.ai33.pro/v1/task/task-123" in url:
                return MockResponse(json.dumps({"status": "success", "audio_url": "/download/test.wav"}).encode("utf-8"))
            # 3. Audio download request
            if "download/test.wav" in url:
                return MockResponse(self.mock_wav_bytes)
            raise ValueError(f"Unexpected URL request: {url}")
            
        mock_urlopen.side_effect = side_effect
        
        params = {
            "outputDir": str(self.user_data / "output"),
            "apiVoiceId": "test-voice-id",
            "apiProvider": "edge",
            "apiWorkers": 1,
            "jobId": "job-ai33-test",
            "speed": 1.0
        }
        entries = [{"id": 1, "text": "Xin chào thế giới"}]
        
        result = self.worker._srt_api_generate("ai33", params, entries)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "completed")
        self.assertEqual(result["items"][0]["duration"], 1.0)
        self.assertTrue(Path(result["items"][0]["file"]).is_file())

    @patch('urllib.request.urlopen')
    @patch('backend.worker.main.emit')
    def test_srt_api_generate_aimax(self, mock_emit, mock_urlopen):
        poll_count = 0
        def side_effect(request, **kwargs):
            nonlocal poll_count
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            # 1. Generate task request
            if "aimaxstudio.com/api/v1/tts/generate" in url:
                return MockResponse(json.dumps({"job_id": "job-123"}).encode("utf-8"))
            # 2. Status check request (simulate one poll delay)
            if "aimaxstudio.com/api/v1/tts/jobs/job-123" in url:
                poll_count += 1
                if poll_count < 2:
                    return MockResponse(json.dumps({"status": "running"}).encode("utf-8"))
                return MockResponse(json.dumps({"status": "completed", "audio_url": "/download/test.wav"}).encode("utf-8"))
            # 3. Audio download request
            if "download/test.wav" in url:
                return MockResponse(self.mock_wav_bytes)
            raise ValueError(f"Unexpected URL request: {url}")
            
        mock_urlopen.side_effect = side_effect
        
        params = {
            "outputDir": str(self.user_data / "output_aimax"),
            "apiVoiceId": "test-voice-id",
            "apiProvider": "minimax",
            "apiModel": "speech-2.8-hd",
            "apiWorkers": 1,
            "jobId": "job-aimax-test",
            "speed": 1.0
        }
        entries = [{"id": 1, "text": "Hôm nay trời đẹp"}]
        
        result = self.worker._srt_api_generate("aimax", params, entries)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "completed")
        self.assertEqual(result["items"][0]["duration"], 1.0)
        self.assertTrue(Path(result["items"][0]["file"]).is_file())


if __name__ == "__main__":
    unittest.main()
