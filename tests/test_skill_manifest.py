import json
import unittest
from pathlib import Path


class SkillManifestTests(unittest.TestCase):
    def test_skill_manifest_exists_and_wiring_is_valid(self):
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "skill.json"
        self.assertTrue(manifest_path.exists(), "skill.json must exist at repository root")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("name"), "watch")

        commands = manifest.get("telegramCommands")
        self.assertIsInstance(commands, list)
        self.assertGreaterEqual(len(commands), 1)

        command = commands[0]
        self.assertEqual(command.get("command"), "watch")
        self.assertEqual(command.get("handler"), "scripts/watch_session.py")


if __name__ == "__main__":
    unittest.main()
