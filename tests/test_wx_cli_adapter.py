import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from wechat_feedback_app.collector import collect_fixture_messages, collect_messages
from wechat_feedback_app.config import WxCliConfig, load_config
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.wx_cli_adapter import (
    run_wx_cli_json,
    test_connection as wx_cli_test_connection,
    wx_cli_readiness,
)


def write_fake_wx(root: Path, body: str) -> Path:
    script = root / "fake_wx.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    script.chmod(0o755)
    return script


class WxCliAdapterTest(unittest.TestCase):
    def test_connection_ok_parses_json_sessions_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                import json
                print(json.dumps({"sessions": [{"id": "s1", "name": "测试群"}]}))
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = wx_cli_test_connection(config)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["error_code"], "")
            self.assertEqual(result["command"], "sessions --json")
            self.assertEqual(result["session_count"], "1")
            self.assertNotIn("测试群", str(result))

    def test_connection_ok_parses_yaml_sessions_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                print("sessions:\\n  - id: s1\\n    name: 测试群")
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = wx_cli_test_connection(config)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["session_count"], "1")

    def test_missing_binary_returns_missing_binary(self):
        config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
        config.wx_cli = WxCliConfig(
            mode="real",
            binary="/path/that/does/not/exist/wx",
            timeout_seconds=1,
        )

        result = wx_cli_test_connection(config)

        self.assertEqual(result["status"], "missing_binary")

    def test_missing_binary_readiness_includes_repair_suggestion(self):
        config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
        config.wx_cli = WxCliConfig(
            mode="real",
            binary="/path/that/does/not/exist/wx",
            timeout_seconds=1,
        )

        result = wx_cli_readiness(config)

        self.assertEqual(result["status"], "missing_binary")
        self.assertEqual(result["configured_binary"], "/path/that/does/not/exist/wx")
        self.assertEqual(result["binary_path"], "")
        self.assertIn("config/app.yaml", result["next_action"])
        self.assertIn("wx", result["next_action"])

    def test_parse_error_for_unparseable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                print("not-json-or-yaml: [")
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = wx_cli_test_connection(config)

            self.assertEqual(result["status"], "parse_error")
            self.assertEqual(result["error_code"], "parse_error")

    def test_connection_parse_error_does_not_return_raw_session_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                print("not structured output with 敏感会话 and wxid_sensitive")
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = wx_cli_test_connection(config)

            self.assertEqual(result["status"], "parse_error")
            self.assertEqual(result["error_code"], "parse_error")
            self.assertEqual(result["session_count"], "0")
            self.assertNotIn("stdout_preview", result)
            self.assertNotIn("stderr_preview", result)
            self.assertNotIn("parsed", result)
            self.assertNotIn("敏感会话", str(result))
            self.assertNotIn("wxid_sensitive", str(result))

    def test_timeout_returns_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                import time
                time.sleep(2)
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=1)

            result = wx_cli_test_connection(config)

            self.assertEqual(result["status"], "timeout")

    def test_real_mode_failed_collection_records_failure_without_polluting_fixture_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")

            conn = connect(config.database.path)
            init_db(conn)
            fixture = collect_fixture_messages(config, conn)
            raw_before = conn.execute("select count(*) from raw_messages").fetchone()[0]
            item_before = conn.execute("select count(*) from candidate_items").fetchone()[0]

            config.wx_cli = WxCliConfig(
                mode="real",
                binary="/path/that/does/not/exist/wx",
                timeout_seconds=1,
                real_read_enabled=True,
            )
            real = collect_messages(config, conn)
            raw_after = conn.execute("select count(*) from raw_messages").fetchone()[0]
            item_after = conn.execute("select count(*) from candidate_items").fetchone()[0]
            latest = conn.execute(
                "select status, error_code from collection_runs order by id desc limit 1"
            ).fetchone()

            self.assertEqual(fixture.status, "success")
            self.assertEqual(real.status, "failed")
            self.assertEqual(real.error_code, "missing_binary")
            self.assertEqual(raw_before, raw_after)
            self.assertEqual(item_before, item_after)
            self.assertEqual(latest["status"], "failed")
            self.assertEqual(latest["error_code"], "missing_binary")

    def test_run_wx_cli_json_maps_stderr_errors_to_status_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                import sys
                sys.stderr.write("permission denied while opening config")
                sys.exit(13)
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = run_wx_cli_json(config, ["sessions", "--json"])

            self.assertEqual(result.status, "permission_denied")
            self.assertIn("permission", result.message.lower())

    def test_run_wx_cli_json_maps_not_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                import sys
                sys.stderr.write("wx-cli not initialized: missing config")
                sys.exit(2)
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = run_wx_cli_json(config, ["sessions", "--json"])

            self.assertEqual(result.status, "not_initialized")

    def test_run_wx_cli_json_maps_wechat_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                """\
                #!/usr/bin/env python3
                import sys
                sys.stderr.write("WeChat not running or not logged in")
                sys.exit(3)
                """,
            )
            config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
            config.wx_cli = WxCliConfig(mode="real", binary=str(fake), timeout_seconds=2)

            result = run_wx_cli_json(config, ["sessions", "--json"])

            self.assertEqual(result.status, "wechat_not_running")


if __name__ == "__main__":
    unittest.main()
