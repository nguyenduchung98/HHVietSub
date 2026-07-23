import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.gemini_translation_service import GeminiTranslationService


class MockResponse:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False


class TestGeminiTranslationService(unittest.TestCase):
    def test_api_response_is_deduplicated_and_reports_missing_ids(self):
        translated = json.dumps([
            {"id": 2, "translated": "Hai"},
            {"id": 1, "translated": "Một"},
            {"id": 2, "translated": "Hai mới"},
            {"id": 999, "translated": "Không dùng"},
        ], ensure_ascii=False)
        payload = {"candidates": [{"content": {"parts": [{"text": translated}]}}]}
        service = GeminiTranslationService(Path("missing"))
        with patch("backend.services.gemini_translation_service.urllib.request.urlopen", return_value=MockResponse(payload)):
            result = service.translate_api({
                "apiKey": "secret", "model": "gemini-test", "entries": [
                    {"id": 1, "text": "One"}, {"id": 2, "text": "Two"}, {"id": 3, "text": "Three"},
                ]
            })
        self.assertEqual([item["id"] for item in result["results"]], [1, 2])
        self.assertEqual(result["results"][1]["translated"], "Hai mới")
        self.assertEqual(result["missing"], [3])

    def test_invalid_model_and_duplicate_input_ids_are_rejected_before_network(self):
        service = GeminiTranslationService(Path("missing"))
        with patch("backend.services.gemini_translation_service.urllib.request.urlopen") as urlopen:
            with self.assertRaises(ValueError):
                service.translate_api({"apiKey": "secret", "model": "../bad", "entries": [{"id": 1, "text": "a"}]})
            with self.assertRaises(ValueError):
                service.translate_api({"apiKey": "secret", "model": "gemini-test", "entries": [{"id": 1, "text": "a"}, {"id": 1, "text": "b"}]})
        urlopen.assert_not_called()

    def test_browser_monkey_patch_is_restored_when_constructor_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config.json").write_text(json.dumps({"endpoint": "https://gemini.google.com/app"}), encoding="utf-8")
            package = types.ModuleType("services")
            package.__path__ = []
            module = types.ModuleType("services.translator_service")
            original_builder = lambda chunk, rule: "original"
            module.build_chunk_text = original_builder
            module.DEFAULT_INSTRUCTION = "rules"
            module.BrowserConfig = lambda **kwargs: kwargs
            module.chunk_entries = lambda entries, size: [entries]
            module.translate_chunk_with_retries = lambda **kwargs: {}

            class BrokenTranslator:
                def __init__(self, **kwargs):
                    raise RuntimeError("constructor failed")
            module.SeleniumGeminiTranslator = BrokenTranslator

            with patch.dict(sys.modules, {"services": package, "services.translator_service": module}):
                with self.assertRaisesRegex(RuntimeError, "constructor failed"):
                    GeminiTranslationService(root).translate_browser({
                        "entries": [{"id": 1, "text": "Hello"}], "gemUrl": "https://gemini.google.com/app"
                    })
            self.assertIs(module.build_chunk_text, original_builder)


if __name__ == "__main__":
    unittest.main()
