import json
import tempfile
import unittest
from pathlib import Path

from backend.services.srt_job_service import SrtJobService


class TestSrtJobService(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.user_data = Path(self.temporary.name)
        self.events = []
        self.service = SrtJobService(self.user_data, self.events.append, retention=10)

    def tearDown(self):
        self.temporary.cleanup()

    def test_save_is_atomic_and_latest_skips_corrupt_files(self):
        self.service.save({"jobId": "srt-1", "state": "running"})
        self.assertFalse((self.service.folder / "srt-1.json.tmp").exists())
        (self.service.folder / "newer.json").write_text("not-json", encoding="utf-8")
        self.assertEqual(self.service.latest()["jobId"], "srt-1")

    def test_invalid_and_duplicate_job_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.path("../../escape")
        self.service.register("srt-safe")
        with self.assertRaises(ValueError):
            self.service.register("srt-safe")

    def test_control_updates_events_and_external_control_file(self):
        control_path = self.user_data / "control.json"
        control = self.service.register("srt-control", control_path)
        paused = self.service.control("srt-control", "pause")
        self.assertTrue(control["pause"].is_set())
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(json.loads(control_path.read_text(encoding="utf-8"))["state"], "paused")
        self.service.control("srt-control", "cancel")
        self.assertTrue(control["cancel"].is_set())
        self.assertEqual(self.events[-1]["event"], "srt.voice.job")

    def test_retention_keeps_only_latest_completed_jobs(self):
        for index in range(12):
            self.service.save({"jobId": f"srt-{index}", "state": "completed"})
        self.assertEqual(len(list(self.service.folder.glob("*.json"))), 10)

    def test_remove_is_idempotent(self):
        self.service.register("srt-remove")
        self.service.remove("srt-remove")
        self.service.remove("srt-remove")
        with self.assertRaises(ValueError):
            self.service.control("srt-remove", "pause")


if __name__ == "__main__":
    unittest.main()
