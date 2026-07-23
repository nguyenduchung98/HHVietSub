import unittest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.worker.main import (
    normalize_language,
    slugify,
    format_srt_time,
    build_srt,
    sanitize_json_value,
    resolve_runtime_path,
)

try:
    from backend.engines.capcut_project_v1 import _safe_project_name, _plain
    CAPCUT_ENGINE_AVAILABLE = True
except Exception:
    CAPCUT_ENGINE_AVAILABLE = False


class TestWorkerUtils(unittest.TestCase):
    def test_normalize_language(self):
        self.assertEqual(normalize_language("vi"), "Tiếng Việt")
        self.assertEqual(normalize_language("vietnamese"), "Tiếng Việt")
        self.assertEqual(normalize_language("tiếng việt"), "Tiếng Việt")
        self.assertEqual(normalize_language("   Tiếng Việt  "), "Tiếng Việt")
        
        self.assertEqual(normalize_language("en"), "English")
        self.assertEqual(normalize_language("english"), "English")
        self.assertEqual(normalize_language("   English  "), "English")
        
        self.assertEqual(normalize_language("fr"), "fr")
        self.assertEqual(normalize_language("japanese"), "japanese")
        self.assertEqual(normalize_language(None), "Chưa xác định")

    def test_slugify(self):
        self.assertEqual(slugify("Giọng kể chuyện ấm áp"), "giong-ke-chuyen-am-ap")
        self.assertEqual(slugify("Ban Mai"), "ban-mai")
        self.assertEqual(slugify("Đức Hùng"), "duc-hung")
        self.assertEqual(slugify("Voice123 !@#"), "voice123")
        # Empty case should fallback to timestamped name
        empty_slug = slugify("!!!")
        self.assertTrue(empty_slug.startswith("voice-"))

    def test_format_srt_time(self):
        self.assertEqual(format_srt_time(0.0), "00:00:00,000")
        self.assertEqual(format_srt_time(1.5), "00:00:01,500")
        self.assertEqual(format_srt_time(61.023), "00:01:01,023")
        self.assertEqual(format_srt_time(3600.0), "01:00:00,000")
        self.assertEqual(format_srt_time(3661.123), "01:01:01,123")

    def test_build_srt(self):
        text = "Hello world. This is a test! Beautiful day."
        srt_content = build_srt(text, 9.0)
        self.assertIn("1\n00:00:00,000 --> 00:00:02", srt_content)
        self.assertIn("Hello world.", srt_content)
        self.assertIn("This is a test!", srt_content)
        self.assertIn("Beautiful day.", srt_content)

    def test_sanitize_json_value(self):
        # Surrogates and non-ASCII strings handling
        sanitized = sanitize_json_value("lỗi\udc8dunicode")
        self.assertNotIn("\udc8d", sanitized)
        # List check
        sanitized_list = sanitize_json_value(["ok", "lỗi\udc8d"])
        self.assertEqual(sanitized_list[0], "ok")
        self.assertNotIn("\udc8d", sanitized_list[1])
        # Dict check
        sanitized_dict = sanitize_json_value({"key": "lỗi\udc8d"})
        self.assertNotIn("\udc8d", sanitized_dict["key"])
        self.assertEqual(sanitize_json_value(123), 123)

    def test_resolve_runtime_path_prefers_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"HHVIETSUB_TEST_ROOT": folder}):
                self.assertEqual(resolve_runtime_path("HHVIETSUB_TEST_ROOT", ROOT), Path(folder).resolve())

    def test_resolve_runtime_path_uses_first_existing_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing"
            existing = Path(folder) / "existing"
            existing.mkdir()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HHVIETSUB_TEST_ROOT", None)
                self.assertEqual(resolve_runtime_path("HHVIETSUB_TEST_ROOT", missing, existing), existing.resolve())


class TestCapCutProjectUtils(unittest.TestCase):
    @unittest.skipUnless(CAPCUT_ENGINE_AVAILABLE, "CapCut V1 Engine dependencies are not fully available")
    def test_safe_project_name(self):
        self.assertEqual(_safe_project_name("Project/Test*Name?"), "Project-Test-Name-")
        self.assertEqual(_safe_project_name("  Trim  Name  "), "Trim  Name")
        # Length constraint checks
        long_name = "a" * 100
        self.assertEqual(len(_safe_project_name(long_name)), 80)

    @unittest.skipUnless(CAPCUT_ENGINE_AVAILABLE, "CapCut V1 Engine dependencies are not fully available")
    def test_plain(self):
        self.assertEqual(_plain("Mẫu Template"), "mau template")
        self.assertEqual(_plain("Đồng Bộ Phụ Đề"), "dong bo phu de")


if __name__ == "__main__":
    unittest.main()
