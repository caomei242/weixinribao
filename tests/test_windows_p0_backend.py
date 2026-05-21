from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, PersonConfig, SessionConfig, WxCliConfig, load_config
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.routes import (
    archive_monitor_group_payload,
    daily_center_payload,
    daily_generation_status_payload,
    delete_monitor_group_payload,
    generate_daily_report_payload,
    internal_people_payload,
    internal_people_suggestions_payload,
    messages_v1_payload,
    monitor_group_detail_payload,
    monitor_groups_payload,
    save_internal_person_payload,
    save_monitor_group_payload,
    windows_readiness_payload,
)


class WindowsP0BackendTest(unittest.TestCase):
    def test_windows_config_sample_is_isolated_and_default_real_read_off(self):
        root = Path(__file__).resolve().parents[1]
        sample = root / "config" / "app.windows.example.yaml"
        config = load_config(sample, root=root)

        payload = windows_readiness_payload(config)
        sample_text = sample.read_text(encoding="utf-8")

        self.assertTrue(payload["config_sample_exists"])
        self.assertFalse(payload["real_read_enabled"])
        self.assertEqual(payload["profile"], "windows_formal")
        self.assertEqual(payload["config_isolation_status"], "ok")
        self.assertEqual(payload["path_isolation"]["status"], "ok")
        self.assertFalse(payload["config_root"]["path_returned"])
        self.assertFalse(payload["wx_cli"]["binary_path_returned"])
        self.assertFalse(payload["wechat_connection"]["session_count_returned"])
        self.assertIn(
            payload["wx_cli"]["connection_status"],
            {"missing_binary", "permission_denied", "needs_connection_test"},
        )
        self.assertFalse(config.wx_cli.real_read_enabled)
        self.assertNotIn("/Users/gd", sample_text)
        self.assertNotIn("襄城县", sample_text)
        self.assertNotIn("Mac", sample_text)
        self._assert_no_sensitive_values(payload, root)

    def test_windows_readiness_sanitizes_mac_development_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "app.windows.example.yaml").write_text(
                "wx_cli:\n  real_read_enabled: false\n", encoding="utf-8"
            )
            config = AppConfig(
                root=root,
                database=type("Database", (), {"path": "/Users/gd/private/db.sqlite3"})(),
                export=type("Export", (), {"directory": "/Users/gd/private/exports"})(),
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/Users/gd/private/wx",
                    real_read_enabled=False,
                    real_allowed_session="Mac测试会话",
                ),
                sessions=[SessionConfig("mac-session", "Mac测试会话")],
            )

            payload = windows_readiness_payload(config)
            text = json.dumps(payload, ensure_ascii=False)

            self.assertTrue(payload["mac_development_config_detected"])
            self.assertEqual(payload["config_isolation_status"], "needs_review")
            self.assertEqual(payload["path_isolation"]["status"], "needs_review")
            self.assertIn("[路径已脱敏]", text)
            self.assertNotIn("/Users/gd/private", text)
            self.assertNotIn("Mac测试会话", text)
            self._assert_no_sensitive_values(payload, root)

    def test_daily_center_first_screen_focus_and_monitor_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "verified",
                        "已验证群",
                        customer_name="客户A",
                        module_name="售后",
                        owner_name="负责人A",
                        verification_status="verified",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
                    ),
                    SessionConfig(
                        "pending",
                        "待验证群",
                        verification_status="pending_verification",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
                    ),
                ],
            )
            self._insert_candidate(conn, "P0-001", "pending", "2026-05-19T09:00:00+08:00")
            self._insert_candidate(conn, "OLD-001", "pending", "2026-05-18T09:00:00+08:00")
            conn.execute(
                """
                insert into collection_runs (mode, started_at, finished_at, status, error_code)
                values ('fixture', '2026-05-19T09:00:00+08:00',
                        '2026-05-19T09:01:00+08:00', 'failed', 'timeout')
                """
            )
            conn.commit()

            payload = daily_center_payload(config, conn, "2026-05-19")

            self.assertEqual(payload["summary"]["monitor_group_count"], 1)
            self.assertEqual(payload["today_focus"]["title"], "今天最要跟进")
            self.assertEqual(payload["today_focus"]["status_label"], "需要处理")
            self.assertIn("timeout", payload["today_focus"]["failure_reason_label"])
            human_text = json.dumps(payload["today_focus"], ensure_ascii=False)
            for token in ["pending", "local_markdown", "real_trial", "formal_write"]:
                self.assertNotIn(token, human_text)

    def test_internal_people_suggestion_save_aliases_and_downstream_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        "监控群A",
                        module_name="售后",
                        roster_member_names=["小A", "客户甲"],
                    )
                ],
            )
            self._insert_raw_message(conn, "group-a", "监控群A", "小A", "unknown")

            suggestion = internal_people_suggestions_payload(
                config, conn, {"display_name": "小A"}
            )
            saved = save_internal_person_payload(
                config,
                conn,
                {
                    "person_name": "我方A",
                    "wechat_display_name": "小A",
                    "aliases": "A 小A\nAlpha，A",
                    "role": "运营",
                    "modules": ["售后"],
                    "notes": "测试备注",
                },
            )
            listed = internal_people_payload(config, conn)

            self.assertEqual(suggestion["status"], "ok")
            self.assertIn(suggestion["suggestions"][0]["confidence"], {"可能是", "已匹配"})
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(saved["person"]["aliases"], ["我方A", "小A", "A", "Alpha"])
            self.assertEqual(saved["person"]["notes"], "测试备注")
            self.assertGreaterEqual(saved["downstream_status"]["sender_match_count"], 1)
            self.assertEqual(listed["count"], 1)
            self.assertIn("notes", listed["people"][0])
            self.assertEqual(listed["people"][0]["notes"], "测试备注")
            self.assertFalse(saved["real_read_enabled"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_no_sensitive(saved, root)

    def test_internal_people_requires_display_name_for_internal_identifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(root)

            suggestion = internal_people_suggestions_payload(
                config, conn, {"wechat_id": "wxid_internal_only"}
            )
            saved = save_internal_person_payload(
                config, conn, {"wechat_id": "wxid_internal_only"}
            )

            self.assertEqual(suggestion["status"], "requires_display_name")
            self.assertTrue(suggestion["requires_display_name"])
            self.assertEqual(saved["status"], "blocked")
            self.assertTrue(saved["requires_display_name"])
            self.assertNotIn("wxid_internal_only", json.dumps(saved, ensure_ascii=False))
            self._assert_no_sensitive(suggestion, root)

    def test_messages_v1_supports_all_and_single_group_with_local_ui_content_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig("group-a", "监控群A", customer_name="客户A"),
                    SessionConfig("group-b", "监控群B", customer_name="客户B"),
                ],
            )
            self._insert_raw_message(conn, "group-a", "监控群A", "小A", "internal")
            self._insert_raw_message(conn, "group-b", "监控群B", "客户B成员", "customer")
            group_a_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            all_payload = messages_v1_payload(config, conn, "all")
            group_payload = messages_v1_payload(config, conn, group_a_id)

            self.assertEqual(all_payload["count"], 2)
            self.assertEqual(group_payload["count"], 1)
            self.assertEqual(group_payload["messages"][0]["group_id"], group_a_id)
            self.assertEqual(group_payload["messages"][0]["sender_identity_label"], "我方人员")
            self.assertIn("detail_target", group_payload["messages"][0])
            self.assertIn("content_preview", group_payload["messages"][0])
            self.assertIn("content_preview_safe", group_payload["messages"][0])
            text = json.dumps(group_payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("raw_payload_json", text)
            self.assertTrue(group_payload["safety"]["content_returned"])
            self.assertTrue(group_payload["safety"]["content_preview_returned"])
            self.assertFalse(group_payload["safety"]["raw_payload_returned"])
            self._assert_no_sensitive(group_payload, root)

    def test_daily_generation_status_and_preserve_existing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(root)
            idle = daily_generation_status_payload(config, conn, "2026-05-19")
            self.assertEqual(idle["status"], "idle")
            self.assertEqual(idle["feedback_state"], "idle")
            self.assertFalse(idle["running"])
            self.assertFalse(idle["success"])
            self.assertFalse(idle["failed"])

            self._insert_candidate(conn, "GEN-001", "pending", "2026-05-19T09:00:00+08:00")
            generated = generate_daily_report_payload(
                config, conn, {"control_date": "2026-05-19"}
            )
            after = daily_generation_status_payload(config, conn, "2026-05-19")

            self.assertEqual(generated["status"], "generated")
            self.assertEqual(generated["feedback_state"], "success")
            self.assertTrue(generated["success"])
            self.assertFalse(generated["running"])
            self.assertFalse(generated["failed"])
            self.assertEqual(after["status"], "generated")
            self.assertEqual(after["feedback_state"], "success")
            self.assertFalse(generated["report_text_cleared"])
            self.assertFalse(generated["safety"]["formal_write_enabled"])

            old_path = root / "exports" / "old.md"
            old_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_text("OLD_REPORT", encoding="utf-8")
            conn.execute(
                """
                insert into settlement_drafts (draft_date, file_path, item_ids_json, summary_json)
                values ('2026-05-20', ?, '[]', '{}')
                """,
                (str(old_path),),
            )
            conn.commit()
            preserved = generate_daily_report_payload(
                config, conn, {"control_date": "2026-05-20"}
            )
            self.assertTrue(preserved["preserved_previous_report"])
            self.assertTrue(preserved["old_report_preserved"])
            self.assertFalse(preserved["report_text_cleared"])
            self.assertEqual(old_path.read_text(encoding="utf-8"), "OLD_REPORT")

    def test_daily_generation_feedback_failed_keeps_status_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(root)
            blocked_export = root / "blocked-export"
            blocked_export.write_text("not a directory", encoding="utf-8")
            config.export.directory = "blocked-export"
            self._insert_candidate(conn, "FAIL-001", "pending", "2026-05-19T09:00:00+08:00")

            failed = generate_daily_report_payload(
                config, conn, {"control_date": "2026-05-19"}
            )

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["feedback_state"], "failed")
            self.assertTrue(failed["failed"])
            self.assertFalse(failed["running"])
            self.assertFalse(failed["success"])
            self.assertFalse(failed["report_text_cleared"])
            self.assertFalse(failed["old_report_preserved"])
            self.assertEqual(failed["error_code"], "daily_generation_failed")
            self.assertFalse(failed["safety"]["formal_write_enabled"])
            self._assert_no_sensitive(failed, root)

    def test_monitor_group_archive_delete_contract_and_stats_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "verified",
                        "已验证群",
                        verification_status="verified",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
                    ),
                    SessionConfig(
                        "pending",
                        "待验证群",
                        verification_status="pending_verification",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
                    ),
                ],
            )
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            before = monitor_groups_payload(config)
            archived = archive_monitor_group_payload(config, group_id)
            after_archive = monitor_groups_payload(config)
            daily_after_archive = daily_center_payload(config, conn, "2026-05-20")
            confirmation = delete_monitor_group_payload(config, group_id, {})
            deleted = delete_monitor_group_payload(
                config, group_id, {"confirm_delete": True}
            )
            after_delete = monitor_groups_payload(config)
            detail_after_delete = monitor_group_detail_payload(config, group_id, conn)

            self.assertEqual(before["daily_center_count"], 1)
            self.assertTrue(before["actions"]["archive"]["available"])
            self.assertTrue(before["actions"]["delete"]["requires_confirmation"])
            self.assertEqual(archived["status"], "archived")
            self.assertTrue(archived["group"]["archived"])
            self.assertEqual(archived["group"]["status_label"], "已归档")
            self.assertFalse(archived["group"]["counts_in_daily_center"])
            self.assertFalse(archived["group"]["can_archive"])
            self.assertTrue(archived["group"]["can_delete"])
            self.assertEqual(after_archive["archived_count"], 1)
            self.assertEqual(after_archive["daily_center_count"], 0)
            self.assertEqual(daily_after_archive["summary"]["monitor_group_count"], 0)
            self.assertEqual(confirmation["status"], "confirmation_required")
            self.assertTrue(confirmation["requires_confirmation"])
            self.assertFalse(confirmation["deleted"])
            self.assertEqual(deleted["status"], "deleted")
            self.assertTrue(deleted["deleted"])
            self.assertEqual(deleted["counts"]["total_count"], 1)
            self.assertEqual(after_delete["count"], 1)
            self.assertEqual(after_delete["daily_center_count"], 0)
            self.assertEqual(detail_after_delete["status"], "not_found")
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_no_sensitive(archived, root)
            self._assert_no_sensitive(deleted, root)

    def test_monitor_group_create_keeps_safe_first_roster_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                wx_cli=WxCliConfig(mode="real", binary="/bin/echo", real_read_enabled=False),
            )

            def runner(_config, _args):
                from wechat_feedback_app.wx_cli_adapter import WxCliCommandResult

                return WxCliCommandResult(
                    status="parse_error",
                    message="",
                    command="members --json",
                )

            created = save_monitor_group_payload(
                config,
                {
                    "group_name": "Windows新增群",
                    "include_in_daily": True,
                    "verification_status": "pending_verification",
                    "authorize_full_roster_sync_on_create": True,
                },
                conn=conn,
                roster_runner=runner,
            )
            group_id = created["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id, conn)

            self.assertEqual(created["status"], "saved")
            self.assertEqual(created["initial_roster_sync"]["status"], "blocked")
            self.assertFalse(created["group"]["counts_in_daily_center"])
            self.assertEqual(detail["status"], "ok")
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_no_sensitive(created, root)

    def _setup(
        self,
        root: Path,
        sessions: list[SessionConfig] | None = None,
        wx_cli: WxCliConfig | None = None,
    ) -> tuple[AppConfig, sqlite3.Connection]:
        config = AppConfig(
            root=root,
            wx_cli=wx_cli or WxCliConfig(real_read_enabled=False),
            sessions=sessions or [],
            internal_people=[],
        )
        conn = connect(root / "data" / "test.sqlite3")
        init_db(conn)
        return config, conn

    def _insert_raw_message(
        self,
        conn: sqlite3.Connection,
        external_id: str,
        group_name: str,
        sender: str,
        role: str,
    ) -> int:
        row = conn.execute(
            "select id from sessions where external_id = ?", (external_id,)
        ).fetchone()
        if row is None:
            cursor = conn.execute(
                "insert into sessions (external_id, display_name) values (?, ?)",
                (external_id, group_name),
            )
            session_id = int(cursor.lastrowid)
        else:
            session_id = int(row["id"])
        run = conn.execute("select id from collection_runs limit 1").fetchone()
        if run is None:
            cursor = conn.execute(
                """
                insert into collection_runs (
                  mode, started_at, finished_at, status
                )
                values ('fixture', '2026-05-19T09:00:00+08:00',
                        '2026-05-19T09:01:00+08:00', 'success')
                """
            )
            run_id = int(cursor.lastrowid)
        else:
            run_id = int(run["id"])
        cursor = conn.execute(
            """
            insert into raw_messages (
              session_id, sender_display_name, sender_role, sent_at,
              message_type, content_text, content_hash, dedupe_key,
              raw_payload_json, collection_run_id
            )
            values (?, ?, ?, '2026-05-19T09:00:00+08:00',
                    'text', '消息正文测试文本', ?, ?, '{}', ?)
            """,
            (
                session_id,
                sender,
                role,
                f"hash-{external_id}-{sender}",
                f"dedupe-{external_id}-{sender}",
                run_id,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def _insert_candidate(
        self,
        conn: sqlite3.Connection,
        item_code: str,
        status: str,
        first_seen_at: str,
    ) -> int:
        cursor = conn.execute(
            """
            insert into candidate_items (
              item_code, item_type, status, risk_level, risk_tags_json,
              customer_name, channel_name, module_name, title, summary,
              suggested_downstream, aggregate_key, first_seen_at, last_seen_at
            )
            values (?, 'followup', ?, 'none', '[]',
                    '客户A', '', '售后', ?, ?,
                    'manual', ?, ?, ?)
            """,
            (
                item_code,
                status,
                f"{item_code} 标题",
                f"{item_code} 安全摘要 wxid_secret_marker",
                f"agg-{item_code}",
                first_seen_at,
                first_seen_at,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def _assert_no_sensitive(self, payload: object, root: Path) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for forbidden in ["wxid", "key", "salt", "daemon", str(root)]:
            self.assertNotIn(forbidden, text)

    def _assert_no_sensitive_values(self, payload: object, root: Path) -> None:
        values: list[str] = []

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str):
                values.append(value)

        walk(payload)
        text = json.dumps(values, ensure_ascii=False)
        for forbidden in ["wxid", "key", "salt", "daemon", str(root)]:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
