import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rpc.errors import rpc_error
from backend.services.settings_service import SettingsService
from backend.worker.main import Worker


class TestSettingsService(unittest.TestCase):
    def test_voice_settings_are_atomic_and_secret_is_memory_only(self):
        with tempfile.TemporaryDirectory() as folder:
            service = SettingsService(Path(folder))
            result = service.save_voice({
                "mode": "colab", "url": "https://example.test/", "token": "secret-token"
            })
            persisted = json.loads(service.voice_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted, {"mode": "colab", "url": "https://example.test"})
            self.assertEqual(result["token"], "")
            self.assertTrue(result["tokenConfigured"])
            self.assertFalse(service.voice_path.with_suffix(".json.tmp").exists())

    def test_empty_secret_fields_preserve_existing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            service = SettingsService(Path(folder))
            service.save_tts({"ai33Key": "key-one\nkey-two"})
            service.save_tts({"ai33Key": "", "aimaxKey": "key-three"})
            self.assertEqual(service.tts_keys("ai33"), ["key-one", "key-two"])
            self.assertEqual(service.tts_keys("aimax"), ["key-three"])


class TestRpcErrors(unittest.TestCase):
    def test_exception_mapping_is_stable(self):
        self.assertEqual(rpc_error(ValueError("bad"))["code"], -32602)
        self.assertEqual(rpc_error(TimeoutError("slow"))["data"]["kind"], "timeout")
        self.assertEqual(rpc_error(FileNotFoundError("gone"))["code"], -32004)

    def test_worker_uses_method_not_found_code(self):
        with tempfile.TemporaryDirectory() as folder:
            response = Worker(Path(folder)).handle({"id": "1", "method": "missing.route", "params": {}})
            self.assertEqual(response["error"]["code"], -32601)
            self.assertEqual(response["error"]["data"]["kind"], "method_not_found")


if __name__ == "__main__":
    unittest.main()
