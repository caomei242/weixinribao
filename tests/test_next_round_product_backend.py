from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, PersonConfig, SessionConfig, WxCliConfig
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.routes import (
    daily_center_payload,
    internal_people_payload,
    internal_people_suggestions_payload,
    messages_v1_payload,
    monitor_group_detail_payload,
    monitor_groups_payload,
    save_internal_person_payload,
    save_monitor_group_payload,
)


class NextRoundProductBackendTest(unittest.TestCase):
    def test_daily_center_exposes_product_followup_sections_and_safe_report_text(self):
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
                    )
                ],
            )
            self._insert_candidate(conn, "P0-001", "pending", "2026-05-20T09:00:00+08:00")
            self._insert_candidate(conn, "P0-002", "confirmed", "2026-05-20T10:00:00+08:00")
            self._insert_candidate(conn, "OLD-001", "pending", "2026-05-18T09:00:00+08:00")

            payload = daily_center_payload(config, conn, "2026-05-20")

            self.assertEqual(payload["status"], "ok")
            self.assertIn("today_top_followups", payload)
            self.assertIn("unfinished_followups", payload)
            self.assertIn("historical_unfinished", payload)
            self.assertEqual(len(payload["today_top_followups"]), 2)
            self.assertEqual(payload["summary"]["unfinished_followup_count"], 2)
            self.assertEqual(payload["summary"]["historical_unfinished_count"], 1)
            self.assertTrue(payload["report_full_text"])
            self.assertEqual(payload["report_human_text"], payload["report"]["report_human_text"])
            self.assertIn("feedback_state", payload["generation_status"])
            self.assertEqual(payload["source"]["monitor_group_count"], 1)
            self._assert_no_sensitive_values(payload, root)

    def test_monitor_group_options_suggestions_and_save_readback_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        "客户A 售后群",
                        customer_name="客户A",
                        group_type="客户群",
                        customer_stage="交付期",
                        owner_names=["负责人A"],
                        common_contacts=["联系人A"],
                        internal_people=["我方A"],
                        verification_status="verified",
                    )
                ],
                internal_people=[PersonConfig("负责人A", aliases=["我方A"])],
            )

            initial = monitor_groups_payload(config)
            saved = save_monitor_group_payload(
                config,
                {
                    "group_name": "客户A 新售后群",
                    "customer_name": "客户A",
                    "group_type": "客户群",
                    "customer_stage": "交付期",
                    "owner_names": ["负责人A"],
                    "common_contacts": ["联系人A"],
                    "internal_people": ["我方A"],
                    "verification_status": "pending_verification",
                    "daily_monitor_enabled": True,
                    "include_in_daily": True,
                },
                conn=conn,
            )
            detail = monitor_group_detail_payload(
                config, saved["group"]["group_id"], conn
            )

            self.assertIn("field_options", initial)
            self.assertIn("customer_name_options", initial)
            self.assertIn("group_type_options", initial)
            self.assertIn("customer_stage_options", initial)
            self.assertIn("owner_options", initial)
            self.assertIn("save_contract", initial)
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(detail["status"], "ok")
            self.assertEqual(detail["group"]["customer_name"], "客户A")
            self.assertEqual(detail["group"]["group_type"], "客户群")
            self.assertEqual(detail["group"]["customer_stage"], "交付期")
            self.assertIn("负责人A", detail["group"]["owner_names"])
            self.assertFalse(saved["real_read_enabled"])
            self._assert_no_sensitive_values(initial, root)
            self._assert_no_sensitive_values(saved, root)

    def test_internal_people_suggestions_save_and_readback_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig(
                        "group-a",
                        "监控群A",
                        roster_member_names=["同事A", "客户侧A"],
                        internal_people=["同事A"],
                    )
                ],
            )
            self._insert_raw_message(conn, "group-a", "监控群A", "同事A", "unknown")

            suggestion = internal_people_suggestions_payload(
                config, conn, {"display_name": "同事A"}
            )
            saved = save_internal_person_payload(
                config,
                conn,
                {
                    "person_name": "同事A",
                    "wechat_display_name": "同事A",
                    "aliases": "同事A, A同事\n同事A",
                    "role": "技术",
                    "modules": ["售后"],
                    "notes": "本地备注",
                },
            )
            listed = internal_people_payload(config, conn)

            self.assertEqual(suggestion["status"], "ok")
            self.assertGreaterEqual(suggestion["count"], 1)
            self.assertIn("suggested_fields", suggestion["suggestions"][0])
            self.assertIn("suggestion_contract", suggestion)
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(saved["person"]["aliases"], ["同事A", "A同事"])
            self.assertIn("readback_fields", saved)
            self.assertEqual(listed["count"], 1)
            self.assertIn("downstream_status", listed)
            self.assertIn("save_readback_contract", listed)
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_no_sensitive_values(suggestion, root)
            self._assert_no_sensitive_values(saved, root)

    def test_messages_v1_keeps_group_first_without_single_group_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup(
                root,
                sessions=[
                    SessionConfig("group-a", "监控群A", customer_name="客户A"),
                    SessionConfig("group-b", "监控群B", customer_name="客户B"),
                ],
            )
            self._insert_raw_message(conn, "group-a", "监控群A", "发送人A", "customer")
            group_b_id = monitor_groups_payload(config)["groups"][1]["group_id"]

            all_payload = messages_v1_payload(config, conn, "all")
            group_payload = messages_v1_payload(config, conn, group_b_id)

            self.assertEqual(all_payload["status"], "ok")
            self.assertEqual(all_payload["message_count"], 1)
            self.assertEqual(group_payload["status"], "ok")
            self.assertEqual(group_payload["message_count"], 0)
            self.assertTrue(group_payload["single_group_no_fallback"])
            self.assertIn("不会回退展示全部群", group_payload["empty_state_label"])
            self.assertEqual(group_payload["group_first_contract"]["filter_param"], "group_id")
            self._assert_no_sensitive_values(all_payload, root)
            self._assert_no_sensitive_values(group_payload, root)

    def _setup(
        self,
        root: Path,
        sessions: list[SessionConfig] | None = None,
        internal_people: list[PersonConfig] | None = None,
    ) -> tuple[AppConfig, sqlite3.Connection]:
        config = AppConfig(
            root=root,
            wx_cli=WxCliConfig(real_read_enabled=False),
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
                values ('fixture', '2026-05-20T09:00:00+08:00',
                        '2026-05-20T09:01:00+08:00', 'success')
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
            values (?, ?, ?, '2026-05-20T09:00:00+08:00',
                    'text', 'SECRET_BODY', ?, ?, '{}', ?)
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
        for forbidden in ["wxid", "key", "salt", "daemon", str(root), "SECRET_BODY"]:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
