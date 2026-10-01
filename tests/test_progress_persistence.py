import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import coord_tooltip


class ProgressPersistenceTests(unittest.TestCase):
    def test_stale_write_conflicts_without_overwriting_saved_progress(self):
        checks = {key: {} for key in coord_tooltip.CHECK_KEYS}
        checks["alphas"] = {"first": True}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            progress_path = root / ".local" / "progress.json"
            legacy_path = root / "progress.json"
            with (
                patch.object(coord_tooltip, "PROGRESS_PATH", progress_path),
                patch.object(coord_tooltip, "LEGACY_PROGRESS_PATH", legacy_path),
            ):
                first = coord_tooltip.save_progress_file(
                    {
                        "baseRevision": 0,
                        "progress": {
                            "version": 2,
                            "revision": 1,
                            "checks": checks,
                            "breedOwned": {},
                            "prefs": {},
                        },
                    }
                )
                stale_checks = {key: {} for key in coord_tooltip.CHECK_KEYS}
                stale_checks["alphas"] = {"stale": True}
                stale = coord_tooltip.save_progress_file(
                    {
                        "baseRevision": 0,
                        "progress": {
                            "version": 2,
                            "revision": 1,
                            "checks": stale_checks,
                            "breedOwned": {},
                            "prefs": {},
                        },
                    }
                )

                self.assertEqual(first["progress"]["revision"], 1)
                self.assertTrue(stale["conflict"])
                self.assertEqual(stale["progress"]["checks"]["alphas"], {"first": True})
                self.assertEqual(
                    coord_tooltip.load_progress_file()["checks"]["alphas"],
                    {"first": True},
                )

    def test_write_requires_a_base_revision(self):
        result = coord_tooltip.save_progress_file({"checks": {}})
        self.assertTrue(result["invalid"])


if __name__ == "__main__":
    unittest.main()
