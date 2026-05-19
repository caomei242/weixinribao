import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsDeployMaterialsTest(unittest.TestCase):
    def test_windows_docs_and_scripts_exist_with_safe_defaults(self):
        expected = [
            ROOT / "docs" / "windows-deploy.md",
            ROOT / "scripts" / "windows" / "start_server.ps1",
            ROOT / "scripts" / "windows" / "install_task.ps1",
            ROOT / "scripts" / "windows" / "remove_task.ps1",
            ROOT / "scripts" / "windows" / "stop_server.ps1",
            ROOT / "scripts" / "windows" / "health_check.ps1",
        ]
        for path in expected:
            self.assertTrue(path.exists(), f"missing {path}")

        doc = (ROOT / "docs" / "windows-deploy.md").read_text(encoding="utf-8")
        for required in [
            "Python",
            "fixture",
            "real",
            "config\\app.yaml",
            "logs",
            "health_check.ps1",
            "real_collection_disabled",
            "不读取真实聊天正文",
        ]:
            self.assertIn(required, doc)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/windows-deploy.md", readme)

    def test_windows_scripts_do_not_contain_message_read_commands(self):
        scripts = list((ROOT / "scripts" / "windows").glob("*.ps1"))
        self.assertGreaterEqual(len(scripts), 4)
        forbidden = re.compile(r"\b(history|new_messages)\b", re.IGNORECASE)
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            self.assertNotRegex(text, forbidden, f"unsafe wx command in {script}")
            self.assertNotIn("config/app.yaml", text)
            self.assertIn("logs", text)


if __name__ == "__main__":
    unittest.main()
