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
    detected_group_external_id_from_raw,
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
            raw_group_name = "本地可读群 13812345678"
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
            raw_group_name = "本地消息群 13812345678"
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
            self.assertTrue(message["content_text"] == "消息正文 13812345678")
            self.assertTrue(message["content_preview"] == "消息正文 13812345678")
            self.assertTrue(message["message_text"] == "消息正文 13812345678")
            self.assertTrue(message["summary"] == "消息正文 13812345678")
            self.assertNotEqual(message["message_ref"], message["summary"])
            self.assertIn("[敏感信息已脱敏]", groups[1]["group_name_safe"])
            self.assertIn("[敏感信息已脱敏]", message["customer_label_safe"])
            self.assertIn("[敏感信息已脱敏]", message["content_preview_safe"])
            self.assertTrue(payload["safety"]["content_returned"])
            self.assertTrue(payload["safety"]["content_preview_returned"])
            self.assertFalse(payload["safety"]["raw_payload_returned"])
            self.assertTrue(payload["safety"]["local_ui_payload"])
            self.assertFalse(payload["safety"]["report_safe_payload"])
            self.assertEqual(payload["content_text_human_readable_count"], 1)
            self.assertEqual(payload["content_preview_human_readable_count"], 1)
            self.assertEqual(payload["message_text_human_readable_count"], 1)
            self.assertEqual(payload["summary_human_readable_count"], 1)
            self.assertEqual(payload["content_text_message_ref_like_count"], 0)
            self.assertEqual(payload["content_preview_message_ref_like_count"], 0)
            self.assertEqual(payload["summary_message_ref_like_count"], 0)
            self.assertEqual(payload["empty_or_placeholder_content_count"], 0)

            report_payload = config_center_payload(config)
            report_text = json.dumps(report_payload, ensure_ascii=False)
            self.assertNotIn("消息正文 13812345678", report_text)
            self.assert_no_forbidden_report_fields(report_payload)

    def test_messages_do_not_use_message_ref_as_content_preview_or_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[SessionConfig("group-a", "本地消息群")],
            )
            self._insert_raw_message(
                conn,
                "group-a",
                "本地消息群",
                content_text="m-0001",
            )

            groups = message_group_options(config, conn)
            payload = messages_v1_payload(config, conn, groups[1]["group_id"])
            message = payload["messages"][0]

            self.assertEqual(message["message_ref"], "m-0001")
            self.assertEqual(message["content_text"], "")
            self.assertEqual(message["content_preview"], "")
            self.assertEqual(message["message_text"], "")
            self.assertEqual(message["summary"], "")
            self.assertEqual(message["content_status"], "placeholder_only")
            self.assertFalse(message["content_returned"])
            self.assertEqual(payload["rows_with_content_returned"], 0)
            self.assertEqual(payload["content_text_human_readable_count"], 0)
            self.assertEqual(payload["content_preview_human_readable_count"], 0)
            self.assertEqual(payload["message_text_human_readable_count"], 0)
            self.assertEqual(payload["summary_human_readable_count"], 0)
            self.assertEqual(payload["summary_message_ref_like_count"], 0)
            self.assertEqual(payload["content_text_message_ref_like_count"], 0)
            self.assertEqual(payload["content_preview_message_ref_like_count"], 0)
            self.assertEqual(payload["empty_or_placeholder_content_count"], 1)

    def test_empty_or_unsupported_message_gets_human_empty_state_not_ref_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[SessionConfig("group-a", "本地消息群")],
            )
            self._insert_raw_message(
                conn,
                "group-a",
                "本地消息群",
                message_type="image",
                content_text="",
            )

            groups = message_group_options(config, conn)
            payload = messages_v1_payload(config, conn, groups[1]["group_id"])
            message = payload["messages"][0]

            self.assertEqual(message["content_text"], "")
            self.assertEqual(message["content_preview"], "")
            self.assertEqual(message["summary"], "")
            self.assertEqual(message["content_status"], "unsupported_message_type")
            self.assertIn("消息类型", message["content_empty_label"])
            self.assertNotEqual(message["summary"], message["message_ref"])
            self.assertEqual(payload["empty_or_placeholder_content_count"], 1)

    def test_internal_chatroom_id_is_not_used_as_group_display_across_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal_group_id = "123456789012345@chatroom"
            config, conn = self._setup(
                root,
                sessions=[SessionConfig("detected-a", internal_group_id)],
            )
            self._insert_raw_message(conn, "detected-a", internal_group_id)

            monitor_payload = monitor_groups_payload(config)
            detail = monitor_group_detail_payload(
                config, monitor_payload["groups"][0]["group_id"], conn
            )
            groups = message_group_options(config, conn)
            messages = messages_v1_payload(config, conn, groups[1]["group_id"])

            self.assertEqual(monitor_payload["groups"][0]["group_name"], "群名待解析")
            self.assertEqual(
                monitor_payload["groups"][0]["display_name_status"], "unresolved"
            )
            self.assertEqual(
                monitor_payload["groups"][0]["display_name_reason_code"],
                "internal_identifier_only",
            )
            self.assertEqual(detail["group"]["group_name"], "群名待解析")
            self.assertEqual(groups[1]["group_name"], "群名待解析")
            self.assertEqual(groups[1]["group_name_status"], "unresolved")
            self.assertEqual(messages["messages"][0]["group_name"], "群名待解析")
            visible_payload = json.dumps(
                {
                    "monitor": monitor_payload["groups"][0],
                    "detail": detail["group"],
                    "message_group": groups[1],
                    "message": messages["messages"][0],
                },
                ensure_ascii=False,
            )
            self.assertNotIn(internal_group_id, visible_payload)

    def test_unresolved_group_name_backfills_from_local_message_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        "群名待解析",
                        display_name_status="unresolved",
                        display_name_source="session_probe",
                        display_name_reason_code="internal_identifier_only",
                    )
                ],
            )
            self._insert_raw_message(
                conn,
                "group-a",
                "123456789012345@chatroom",
                raw_payload={
                    "chatroom": {
                        "display_name": "本地元数据可读群 13812345678"
                    }
                },
            )

            payload = monitor_groups_payload(config, conn)
            detail = monitor_group_detail_payload(
                config, payload["groups"][0]["group_id"], conn
            )
            groups = message_group_options(config, conn)

            self.assertEqual(
                payload["groups"][0]["group_name"], "本地元数据可读群 13812345678"
            )
            self.assertEqual(payload["groups"][0]["display_name_status"], "resolved")
            self.assertEqual(payload["display_name_backfilled_count"], 1)
            self.assertEqual(payload["monitor_group_count"], 1)
            self.assertEqual(payload["readable_group_label_count"], 1)
            self.assertEqual(payload["unresolved_group_label_count"], 0)
            self.assertEqual(payload["unresolved_with_readable_source_count"], 0)
            self.assertEqual(payload["unresolved_without_readable_source_count"], 0)
            self.assertEqual(
                payload["display_name_diagnostics"]["before_refresh"][
                    "unresolved_with_readable_source_count"
                ],
                1,
            )
            self.assertEqual(detail["group"]["group_name"], "本地元数据可读群 13812345678")
            self.assertEqual(groups[1]["group_name"], "本地元数据可读群 13812345678")
            self.assertEqual(config.sessions[0].display_name_status, "resolved")
            self.assertEqual(config.sessions[0].display_name, "本地元数据可读群 13812345678")

    def test_monitor_groups_display_name_diagnostics_count_current_visible_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            detected_external_id = detected_group_external_id_from_raw(
                "223456789012345@chatroom"
            )
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig("resolved-a", "已解析群"),
                    SessionConfig(
                        detected_external_id,
                        "群名待解析",
                        display_name_status="unresolved",
                        display_name_reason_code="internal_identifier_only",
                    ),
                    SessionConfig(
                        "missing-source",
                        "群名待解析",
                        display_name_status="unresolved",
                        display_name_reason_code="internal_identifier_only",
                    ),
                ],
            )
            self._insert_raw_message(
                conn,
                "223456789012345@chatroom",
                "223456789012345@chatroom",
                raw_payload={
                    "id": "223456789012345@chatroom",
                    "chatroom": {"remarkName": "本地二段解析群 13812345678"},
                },
            )

            payload = monitor_groups_payload(config, conn)

            self.assertEqual(payload["monitor_group_count"], 3)
            self.assertEqual(payload["display_name_backfilled_count"], 1)
            self.assertEqual(payload["readable_group_label_count"], 2)
            self.assertEqual(payload["unresolved_group_label_count"], 1)
            self.assertEqual(payload["unresolved_with_readable_source_count"], 0)
            self.assertEqual(payload["unresolved_without_readable_source_count"], 1)
            before = payload["display_name_diagnostics"]["before_refresh"]
            self.assertEqual(before["readable_group_label_count"], 1)
            self.assertEqual(before["unresolved_group_label_count"], 2)
            self.assertEqual(before["unresolved_with_readable_source_count"], 1)
            self.assertEqual(before["unresolved_without_readable_source_count"], 1)
            resolved = [
                group
                for group in payload["groups"]
                if group["display_name_status"] == "resolved"
            ]
            unresolved = [
                group
                for group in payload["groups"]
                if group["display_name_status"] == "unresolved"
            ]
            self.assertEqual(len(resolved), 2)
            self.assertEqual(len(unresolved), 1)

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

    def test_internal_people_internal_id_requires_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup(Path(tmp))

            suggestion = internal_people_suggestions_payload(
                config, conn, {"wechat_id": "wxid_internal_only"}
            )

            self.assertEqual(suggestion["status"], "requires_display_name")
            self.assertTrue(suggestion["requires_display_name"])
            self.assertEqual(suggestion["count"], 0)
            self.assertNotIn("wxid_internal_only", json.dumps(suggestion, ensure_ascii=False))

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
            "group_name": "候选可读群 13812345678",
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
            self.assertTrue(row["group_label"] == "候选可读群 13812345678")
            self.assertIn("[敏感信息已脱敏]", row["summary_safe"])
        self.assertTrue(followup["customer_label"] == "客户 13812345678")
        self.assertTrue(followup["module_label"] == "模块 13812345678")
        self.assertIn("[敏感信息已脱敏]", followup["customer_label_safe"])

        internal_group_item = dict(item)
        internal_group_item["group_name"] = "123456789012345@chatroom"
        internal_followup = daily_followup_items_payload(
            [internal_group_item], set(), "today_top_followups"
        )[0]
        internal_focus = daily_center_today_focus_payload(
            "2026-05-20",
            [internal_group_item],
            [],
            1,
            {},
            False,
        )["items"][0]
        internal_inbox = build_candidate_inbox_items(
            [internal_group_item], "workspace", set()
        )[0]
        for row in (internal_followup, internal_focus, internal_inbox):
            self.assertEqual(row["group_label"], "群名待解析")
            self.assertEqual(row["group_label_status"], "unresolved")
            self.assertEqual(row["group_label_reason_code"], "internal_identifier_only")

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
        self,
        conn: sqlite3.Connection,
        external_id: str,
        group_name: str,
        raw_payload: dict[str, object] | None = None,
        message_type: str = "text",
        content_text: str = "消息正文 13812345678",
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
                    ?, ?, 'hash-a', 'dedupe-a', ?, ?)
            """,
            (
                session_id,
                message_type,
                content_text,
                json.dumps(raw_payload or {}, ensure_ascii=False),
                int(run.lastrowid),
            ),
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
