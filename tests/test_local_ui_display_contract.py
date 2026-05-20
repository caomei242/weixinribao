from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, PersonConfig, SessionConfig
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.routes import (
    build_candidate_inbox_items,
    config_center_payload,
    daily_center_today_focus_payload,
    daily_followup_items_payload,
    internal_people_payload,
    internal_people_suggestions_payload,
    message_group_options,
    messages_v1_payload,
    monitor_group_detail_payload,
    monitor_groups_payload,
    real_trial_latest_items_payload,
)


class LocalUiDisplayContractTest(unittest.TestCase):
    def test_monitor_groups_main_fields_keep_local_display_values_with_safe_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_group_name = "local-group-12345678@chatroom"
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        raw_group_name,
                        customer_name="客户 13812345678",
                        group_type="客户群 13812345678",
                        module_name="模块 13812345678",
                        customer_stage="阶段 13812345678",
                        owner_names=["负责人 13812345678"],
                    )
                ],
            )

            payload = monitor_groups_payload(config)
            detail = monitor_group_detail_payload(
                config, payload["groups"][0]["group_id"], conn
            )
            group = payload["groups"][0]
            detail_group = detail["group"]

            self.assertTrue(group["group_name"] == raw_group_name)
            self.assertTrue(group["customer_name"] == "客户 13812345678")
            self.assertTrue(group["module_name"] == "模块 13812345678")
            self.assertTrue(detail_group["owner_names"] == ["负责人 13812345678"])
            self.assertIn("[敏感信息已脱敏]", group["group_name_safe"])
            self.assertIn("[敏感信息已脱敏]", group["customer_name_safe"])
            self.assertIn("[敏感信息已脱敏]", detail_group["owner_names_safe"][0])
            self.assert_no_forbidden_report_fields(config_center_payload(config))

    def test_messages_main_fields_keep_group_customer_and_module_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_group_name = "local-message-group-12345678@chatroom"
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        raw_group_name,
                        customer_name="客户 13812345678",
                        module_name="模块 13812345678",
                    )
                ],
            )
            self._insert_raw_message(conn, "group-a", raw_group_name)

            groups = message_group_options(config, conn)
            payload = messages_v1_payload(config, conn, groups[1]["group_id"])
            message = payload["messages"][0]

            self.assertTrue(groups[1]["group_name"] == raw_group_name)
            self.assertTrue(groups[1]["customer_label"] == "客户 13812345678")
            self.assertTrue(message["group_name"] == raw_group_name)
            self.assertTrue(message["customer_label"] == "客户 13812345678")
            self.assertTrue(message["module_label"] == "模块 13812345678")
            self.assertIn("[敏感信息已脱敏]", groups[1]["group_name_safe"])
            self.assertIn("[敏感信息已脱敏]", message["customer_label_safe"])
            self.assertFalse(payload["safety"]["content_returned"])

    def test_internal_people_main_fields_keep_display_values_with_safe_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                internal_people=[
                    PersonConfig(
                        "人员 13812345678",
                        aliases=["别名 13812345678"],
                        wechat_display_name="微信名 13812345678",
                        modules=["模块 13812345678"],
                        notes="备注 13812345678",
                    )
                ],
            )

            payload = internal_people_payload(config, conn)
            suggestion = internal_people_suggestions_payload(
                config, conn, {"query": "人员 13812345678"}
            )
            person = payload["people"][0]
            first_suggestion = suggestion["suggestions"][0]

            self.assertTrue(person["person_name"] == "人员 13812345678")
            self.assertTrue(person["wechat_display_name"] == "微信名 13812345678")
            self.assertTrue(person["modules"] == ["模块 13812345678"])
            self.assertTrue(person["notes"] == "备注 13812345678")
            self.assertTrue(first_suggestion["person_name"] == "人员 13812345678")
            self.assertIn("[敏感信息已脱敏]", person["person_name_safe"])
            self.assertIn("[敏感信息已脱敏]", first_suggestion["person_name_safe"])

    def test_candidate_and_daily_ui_fields_keep_main_text_while_safe_fields_redact(self):
        item = {
            "id": 1,
            "item_code": "UI-001",
            "item_type": "bug",
            "status": "pending",
            "risk_level": "none",
            "risk_tags": [],
            "customer_name": "客户 13812345678",
            "module_name": "模块 13812345678",
            "title": "标题 13812345678",
            "summary": "摘要 13812345678",
        }

        followup = daily_followup_items_payload([item], set(), "today_top_followups")[0]
        focus = daily_center_today_focus_payload(
            "2026-05-20",
            [item],
            [],
            1,
            {},
            False,
        )["items"][0]
        inbox = build_candidate_inbox_items([item], "workspace", set())[0]

        for row in (followup, focus, inbox):
            self.assertTrue(row["summary"] == "摘要 13812345678")
            self.assertIn("[敏感信息已脱敏]", row["summary_safe"])
        self.assertTrue(followup["customer_label"] == "客户 13812345678")
        self.assertTrue(followup["module_label"] == "模块 13812345678")
        self.assertIn("[敏感信息已脱敏]", followup["customer_label_safe"])

    def test_real_trial_latest_items_keep_main_title_summary_and_safe_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "real_trial_recent50_20260520-221500.sqlite3"
            db_path.parent.mkdir(parents=True)
            self._write_real_trial_item_db(db_path)
            config = AppConfig(root=root)

            payload = real_trial_latest_items_payload(config)
            item = payload["items"][0]

            self.assertTrue(item["title"] == "标题 13812345678")
            self.assertTrue(item["summary"] == "摘要 13812345678")
            self.assertTrue(item["module_name"] == "模块 13812345678")
            self.assertIn("[敏感信息已脱敏]", item["title_safe"])
            self.assertIn("[敏感信息已脱敏]", item["summary_safe"])
            self.assertNotIn("content_text", json.dumps(payload, ensure_ascii=False))
            self.assertNotIn(str(root), json.dumps(payload, ensure_ascii=False))

    def assert_no_forbidden_report_fields(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for forbidden in (
            "sqlite_path",
            "db_path",
            "database_path",
            "member_name_options",
            "raw_payload",
        ):
            self.assertNotIn(forbidden, text)

    def _setup(
        self,
        root: Path,
        *,
        sessions: list[SessionConfig] | None = None,
        internal_people: list[PersonConfig] | None = None,
    ) -> tuple[AppConfig, sqlite3.Connection]:
        config = AppConfig(
            root=root,
            sessions=sessions or [],
            internal_people=internal_people or [],
        )
        conn = connect(root / "data" / "test.sqlite3")
        init_db(conn)
        return config, conn

    def _insert_raw_message(
        self, conn: sqlite3.Connection, external_id: str, group_name: str
    ) -> None:
        cursor = conn.execute(
            "insert into sessions (external_id, display_name, customer_name, module_name) values (?, ?, ?, ?)",
            (external_id, group_name, "客户 13812345678", "模块 13812345678"),
        )
        session_id = int(cursor.lastrowid)
        run = conn.execute(
            """
            insert into collection_runs (mode, started_at, finished_at, status)
            values ('fixture', '2026-05-20T09:00:00+08:00',
                    '2026-05-20T09:01:00+08:00', 'success')
            """
        )
        conn.execute(
            """
            insert into raw_messages (
              session_id, sender_display_name, sender_role, sent_at,
              message_type, content_text, content_hash, dedupe_key,
              raw_payload_json, collection_run_id
            )
            values (?, '发送人', 'customer', '2026-05-20T09:02:00+08:00',
                    'text', 'SECRET_BODY', 'hash-a', 'dedupe-a', '{}', ?)
            """,
            (session_id, int(run.lastrowid)),
        )
        conn.commit()

    def _write_real_trial_item_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                create table candidate_items (
                  id integer primary key,
                  item_code text,
                  item_type text,
                  status text,
                  risk_level text,
                  risk_tags_json text,
                  module_name text,
                  title text,
                  summary text,
                  suggested_downstream text,
                  first_seen_at text,
                  last_seen_at text
                )
                """
            )
            conn.execute(
                """
                create table candidate_item_messages (
                  item_id integer,
                  raw_message_id integer
                )
                """
            )
            conn.execute(
                """
                insert into candidate_items (
                  id, item_code, item_type, status, risk_level, risk_tags_json,
                  module_name, title, summary, suggested_downstream,
                  first_seen_at, last_seen_at
                )
                values (
                  1, 'UI-TRIAL-001', 'bug', 'pending', 'none', '[]',
                  '模块 13812345678', '标题 13812345678', '摘要 13812345678',
                  'tech', '2026-05-20T09:00:00+08:00', '2026-05-20T09:10:00+08:00'
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
