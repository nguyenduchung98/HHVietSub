import tempfile
import unittest
from pathlib import Path

from backend.services.subtitle_service import SubtitleService, normalize_timing


class TestSubtitleService(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_parse_bom_dot_milliseconds_and_malformed_blocks(self):
        source = self.folder / "source.srt"
        source.write_text(
            "\ufeff1\n00:00:00.100 --> 00:00:01.500\nHello\n\n"
            "broken block\n\n"
            "1\n00:00:02,000 --> 00:00:03,000\nWorld\n",
            encoding="utf-8",
        )
        result = SubtitleService.parse(source)
        self.assertEqual(len(result["entries"]), 2)
        self.assertEqual(result["entries"][0]["start"], "00:00:00,100")
        self.assertNotEqual(result["entries"][0]["id"], result["entries"][1]["id"])
        self.assertGreaterEqual(len(result["warnings"]), 2)

    def test_save_is_atomic_and_prefers_translation(self):
        source = self.folder / "source.srt"
        source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        result = SubtitleService.save(source, [{
            "start": "00:00:00,000", "end": "00:00:01,000", "source": "Hello", "translated": "Xin chào"
        }])
        output = Path(result["path"])
        self.assertIn("Xin chào", output.read_text(encoding="utf-8"))
        self.assertFalse(output.with_suffix(".srt.tmp").exists())

    def test_output_cannot_escape_source_directory(self):
        source = self.folder / "source.srt"
        source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        outside = self.folder.parent / "outside.srt"
        with self.assertRaises(ValueError):
            SubtitleService.save(source, [{"start": "00:00:00,000", "end": "00:00:01,000", "source": "Hello"}], str(outside))

    def test_invalid_timing_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_timing("00:00:02,000 --> 00:00:01,000")
        with self.assertRaises(ValueError):
            normalize_timing("00:99:00,000 --> 00:99:01,000")


if __name__ == "__main__":
    unittest.main()
