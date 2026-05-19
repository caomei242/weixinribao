import json
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path

from wechat_feedback_app.collector import collect_fixture_messages, collect_messages
from wechat_feedback_app.config import (
    SessionConfig,
    WxCliConfig,
    load_config,
)
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.wx_cli_adapter import (
    TRIAL_SESSION_NAME,
    build_history_args,
    fetch_messages,
)


def write_fake_wx(root: Path, body: str) -> Path:
    script = root / "fake_wx.py"
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    script.chmod(0o755)
    return script


def real_trial_config(root: Path, fake_wx: Path) -> object:
    config = load_config(Path("config/app.example.yaml"), root=Path.cwd())
    config.database.path = str(root / "data" / "test.sqlite3")
    config.export.directory = str(root / "exports")
    config.wx_cli = WxCliConfig(
        mode="real",
        binary=str(fake_wx),
        timeout_seconds=2,
        real_read_enabled=True,
        real_allowed_session=TRIAL_SESSION_NAME,
        real_lookback_hours=2,
        real_limit=50,
    )
    config.sessions = [
        SessionConfig(
            external_id=TRIAL_SESSION_NAME,
            display_name=TRIAL_SESSION_NAME,
            customer_name="襄城县大斌网络科技有限公司",
            module_name="试点",
            owner_name="",
            is_whitelisted=True,
            enabled=True,
        )
    ]
    return config


class RealReadTrialTest(unittest.TestCase):
    def test_quoted_false_config_keeps_real_read_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "app.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """\
                    wx_cli:
                      mode: "real"
                      binary: "wx"
                      real_read_enabled: "false"
                    """
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, root=root)

            self.assertFalse(config.wx_cli.real_read_enabled)

    def test_default_real_read_switch_off_blocks_history_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "called.txt"
            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys
                from pathlib import Path
                if sys.argv[1] == "history":
                    Path({str(marker)!r}).write_text("called", encoding="utf-8")
                print(json.dumps({{"sessions": [{{"name": {TRIAL_SESSION_NAME!r}}}] }}, ensure_ascii=False))
                """,
            )
            config = real_trial_config(root, fake)
            config.wx_cli.real_read_enabled = False
            conn = connect(config.database.path)
            init_db(conn)

            result = collect_messages(config, conn)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_code, "real_read_disabled")
            self.assertFalse(marker.exists())

    def test_build_history_args_clamps_to_two_hours_and_fifty_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(root, "#!/usr/bin/env python3\n")
            config = real_trial_config(root, fake)
            config.wx_cli.real_lookback_hours = 24
            config.wx_cli.real_limit = 200

            args = build_history_args(config, now=datetime(2026, 5, 15, 17, 30))

            self.assertEqual(
                args,
                [
                    "history",
                    TRIAL_SESSION_NAME,
                    "--since",
                    "2026-05-15 15:30",
                    "-n",
                    "50",
                    "--json",
                ],
            )

    def test_fake_history_json_maps_to_normalized_message_with_fallback_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args_log = root / "args.json"
            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys
                from pathlib import Path

                Path({str(args_log)!r}).write_text(json.dumps(sys.argv[1:], ensure_ascii=False), encoding="utf-8")
                if sys.argv[1:3] == ["sessions", "--json"]:
                    print(json.dumps({{"sessions": [{{"name": {TRIAL_SESSION_NAME!r}}}] }}, ensure_ascii=False))
                elif sys.argv[1] == "history":
                    print(json.dumps({{"messages": [
                        {{
                            "chat": {TRIAL_SESSION_NAME!r},
                            "timestamp": "2026-05-15T16:20:00+08:00",
                            "sender": "FAKE_SENDER",
                            "content": "FAKE 希望 新增 字段",
                            "type": "text"
                        }}
                    ]}}, ensure_ascii=False))
                else:
                    sys.exit(9)
                """,
            )
            config = real_trial_config(root, fake)

            messages = fetch_messages(config, now=datetime(2026, 5, 15, 17, 30))

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].session_external_id, TRIAL_SESSION_NAME)
            self.assertEqual(messages[0].message_external_id, None)
            self.assertEqual(messages[0].local_id, None)
            self.assertEqual(messages[0].sender_display_name, "FAKE_SENDER")
            self.assertEqual(messages[0].content_text, "FAKE 希望 新增 字段")
            self.assertEqual(
                json.loads(args_log.read_text(encoding="utf-8")),
                [
                    "history",
                    TRIAL_SESSION_NAME,
                    "--since",
                    "2026-05-15 15:30",
                    "-n",
                    "50",
                    "--json",
                ],
            )

    def test_whitelist_mismatch_blocks_real_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "called.txt"
            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys
                from pathlib import Path
                if sys.argv[1] == "history":
                    Path({str(marker)!r}).write_text("called", encoding="utf-8")
                print(json.dumps({{"sessions": [{{"name": {TRIAL_SESSION_NAME!r}}}] }}, ensure_ascii=False))
                """,
            )
            config = real_trial_config(root, fake)
            config.sessions = [
                SessionConfig(
                    external_id="other",
                    display_name="白名单外",
                    is_whitelisted=True,
                    enabled=True,
                )
            ]
            conn = connect(config.database.path)
            init_db(conn)

            result = collect_messages(config, conn)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_code, "real_trial_session_not_whitelisted")
            self.assertFalse(marker.exists())

    def test_multiple_enabled_whitelisted_sessions_block_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "history_called.txt"
            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys
                from pathlib import Path
                if sys.argv[1] == "history":
                    Path({str(marker)!r}).write_text("called", encoding="utf-8")
                print(json.dumps({{"messages": []}}, ensure_ascii=False))
                """,
            )
            config = real_trial_config(root, fake)
            config.sessions.append(
                SessionConfig(
                    external_id="extra-session",
                    display_name="额外启用白名单",
                    is_whitelisted=True,
                    enabled=True,
                )
            )
            conn = connect(config.database.path)
            init_db(conn)

            result = collect_messages(config, conn)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_code, "real_trial_whitelist_count_invalid")
            self.assertFalse(marker.exists())

    def test_repeated_real_trial_collection_dedupes_raw_messages_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys

                if sys.argv[1:3] == ["sessions", "--json"]:
                    print(json.dumps({{"sessions": [{{"name": {TRIAL_SESSION_NAME!r}}}] }}, ensure_ascii=False))
                elif sys.argv[1] == "history":
                    print(json.dumps({{"messages": [
                        {{
                            "chat": {TRIAL_SESSION_NAME!r},
                            "timestamp": "2026-05-15T16:40:00+08:00",
                            "sender": "FAKE_SENDER",
                            "content": "FAKE 希望 新增 字段",
                            "type": "text"
                        }}
                    ]}}, ensure_ascii=False))
                else:
                    sys.exit(9)
                """,
            )
            config = real_trial_config(root, fake)
            conn = connect(config.database.path)
            init_db(conn)

            first = collect_messages(config, conn)
            second = collect_messages(config, conn)

            self.assertEqual(first.status, "success")
            self.assertEqual(first.raw_messages_inserted, 1)
            self.assertEqual(first.candidate_items_created, 1)
            self.assertEqual(second.status, "success")
            self.assertEqual(second.raw_messages_inserted, 0)
            self.assertEqual(second.raw_messages_duplicated, 1)
            self.assertEqual(second.candidate_items_created, 0)
            self.assertEqual(conn.execute("select count(*) from raw_messages").fetchone()[0], 1)
            self.assertEqual(conn.execute("select count(*) from candidate_items").fetchone()[0], 1)

    def test_history_failure_records_failed_run_without_polluting_fixture_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")
            conn = connect(config.database.path)
            init_db(conn)
            fixture = collect_fixture_messages(config, conn)
            raw_before = conn.execute("select count(*) from raw_messages").fetchone()[0]
            item_before = conn.execute("select count(*) from candidate_items").fetchone()[0]

            fake = write_fake_wx(
                root,
                f"""\
                #!/usr/bin/env python3
                import json
                import sys
                if sys.argv[1:3] == ["sessions", "--json"]:
                    print(json.dumps({{"sessions": [{{"name": {TRIAL_SESSION_NAME!r}}}] }}, ensure_ascii=False))
                elif sys.argv[1] == "history":
                    print("not-json-or-yaml: [")
                """,
            )
            config.wx_cli = WxCliConfig(
                mode="real",
                binary=str(fake),
                timeout_seconds=2,
                real_read_enabled=True,
                real_allowed_session=TRIAL_SESSION_NAME,
                real_lookback_hours=2,
                real_limit=50,
            )
            config.sessions = [
                SessionConfig(
                    external_id=TRIAL_SESSION_NAME,
                    display_name=TRIAL_SESSION_NAME,
                    customer_name="襄城县大斌网络科技有限公司",
                    is_whitelisted=True,
                    enabled=True,
                )
            ]

            real = collect_messages(config, conn)
            raw_after = conn.execute("select count(*) from raw_messages").fetchone()[0]
            item_after = conn.execute("select count(*) from candidate_items").fetchone()[0]
            latest = conn.execute(
                "select status, error_code from collection_runs order by id desc limit 1"
            ).fetchone()

            self.assertEqual(fixture.status, "success")
            self.assertEqual(real.status, "failed")
            self.assertEqual(real.error_code, "parse_error")
            self.assertEqual(raw_before, raw_after)
            self.assertEqual(item_before, item_after)
            self.assertEqual(latest["status"], "failed")
            self.assertEqual(latest["error_code"], "parse_error")


if __name__ == "__main__":
    unittest.main()
