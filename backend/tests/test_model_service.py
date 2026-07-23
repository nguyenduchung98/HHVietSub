import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.model_service import MODEL_CATALOG, ModelService


class TestModelService(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.events = []
        self.service = ModelService(self.root, self.events.append, self.root / "cache")

    def tearDown(self):
        self.temporary.cleanup()

    def test_catalog_and_download_detection(self):
        self.assertGreaterEqual(len(MODEL_CATALOG), 5)
        repo = MODEL_CATALOG[0]["repo"]
        snapshot = self.service.hub_dir(repo) / "snapshots" / "revision"
        snapshot.mkdir(parents=True)
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
        model = next(item for item in self.service.list_models() if item["repo"] == repo)
        self.assertTrue(model["ready"])
        self.assertEqual(model["status"], "ready")
        self.assertEqual(self.service.snapshot_path(repo), snapshot.resolve())

    def test_snapshot_path_rejects_missing_or_empty_cache(self):
        repo = MODEL_CATALOG[0]["repo"]
        with self.assertRaises(FileNotFoundError):
            self.service.snapshot_path(repo)
        (self.service.hub_dir(repo) / "snapshots" / "empty").mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):
            self.service.snapshot_path(repo)

    def test_download_reservation_is_atomic(self):
        class DeferredThread:
            def __init__(self, *args, **kwargs):
                pass
            def start(self):
                pass

        with patch("backend.services.model_service.threading.Thread", DeferredThread):
            first = self.service.download("omnivoice")
            second = self.service.download("omnivoice")
        self.assertEqual(first["status"], "started")
        self.assertEqual(second["status"], "downloading")

    def test_delete_reports_actual_state_and_removes_cache(self):
        model_path = self.service.hub_dir(MODEL_CATALOG[0]["repo"])
        model_path.mkdir(parents=True)
        (model_path / "weights.bin").write_bytes(b"model")
        result = self.service.delete("omnivoice")
        self.assertTrue(result["deleted"])
        self.assertFalse(model_path.exists())
        self.assertFalse(self.service.delete("omnivoice")["deleted"])

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.delete("../../outside")


if __name__ == "__main__":
    unittest.main()
