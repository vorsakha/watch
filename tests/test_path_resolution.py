import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import watch_session


class PathResolutionTests(unittest.TestCase):
    def test_workspace_priority_watch_then_openclaw_then_ascension(self):
        with patch.dict(
            os.environ,
            {
                "WATCH_WORKSPACE": "/tmp/watch_ws",
                "OPENCLAW_WORKSPACE": "/tmp/openclaw_ws",
                "ASCENSION_WORKSPACE": "/tmp/ascension_ws",
            },
            clear=True,
        ):
            self.assertEqual(watch_session.resolve_workspace_root(), Path("/tmp/watch_ws").resolve())

    def test_workspace_falls_back_to_openclaw(self):
        with patch.dict(os.environ, {"OPENCLAW_WORKSPACE": "/tmp/openclaw_ws"}, clear=True):
            self.assertEqual(watch_session.resolve_workspace_root(), Path("/tmp/openclaw_ws").resolve())

    def test_workspace_falls_back_to_ascension(self):
        with patch.dict(os.environ, {"ASCENSION_WORKSPACE": "/tmp/ascension_ws"}, clear=True):
            self.assertEqual(watch_session.resolve_workspace_root(), Path("/tmp/ascension_ws").resolve())

    def test_workspace_final_fallback_is_home_openclaw_workspace(self):
        with patch.dict(os.environ, {}, clear=True):
            expected = (Path.home() / ".openclaw" / "workspace").resolve()
            self.assertEqual(watch_session.resolve_workspace_root(), expected)

    def test_default_paths_follow_resolved_workspace(self):
        with patch.dict(os.environ, {"WATCH_WORKSPACE": "/tmp/watch_ws"}, clear=True):
            root = watch_session.resolve_workspace_root()
            self.assertEqual((root / "WATCH_LOG.md").resolve(), Path("/tmp/watch_ws/WATCH_LOG.md").resolve())
            self.assertEqual((root / "cache").resolve(), Path("/tmp/watch_ws/cache").resolve())


if __name__ == "__main__":
    unittest.main()
