from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import (
    AppConfig,
    SessionConfig,
    WxCliConfig,
    default_config,
    load_config,
)
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.routes import (
    candidate_resolution_status_payload,
    daily_center_payload,
    daily_settlement_center_payload,
    disable_monitor_group_payload,
    monitor_group_detail_payload,
    monitor_groups_payload,
    save_monitor_group_payload,
)


class DailyCenterMonitorGroupsTest(unittest.TestCase):
    def test_daily_center_counts_report_state_and_field_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "verified-a",
                        "已验证日报群",
                        module_name="订单",
                        owner_name="负责人A",
                        customer_stage="交付期",
                        group_type="客户群",
                        common_contacts=["客户联系人A"],
                        internal_people=["负责人A"],
                        verification_status="verified",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
                    ),
                    SessionConfig(
                        "second-test",
                        "洽姐x稿定电商",
                        module_name="电商设计",
                        owner_name="负责人B",
                        customer_stage="试读验证",
                        group_type="测试群",
                        verification_status="pending_verification",
                        daily_monitor_enabled=True,
                        include_in_daily=False,
                    ),
                    SessionConfig(
                        "not-daily",
                        "不进日报群",
                        verification_status="verified",
                        daily_monitor_enabled=True,
                        include_in_daily=False,
                    ),
                ],
            )
            self._insert_candidate(conn, "N-001", "pending", "2026-05-19T09:00:00+08:00")
            self._insert_candidate(conn, "N-002", "confirmed", "2026-05-19T10:00:00+08:00")
            self._insert_candidate(conn, "H-001", "pending", "2026-05-18T10:00:00+08:00")

            payload = daily_center_payload(config, conn, "2026-05-19")

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["page_title"], "日报中心")
            self.assertEqual(payload["summary"]["monitor_group_count"], 1)
            self.assertEqual(payload["summary"]["new_issue_count"], 2)
            self.assertEqual(payload["summary"]["historical_unfollowed_count"], 1)
            self.assertEqual(payload["summary"]["report_status_label"], "已生成")
            self.assertEqual(payload["summary"]["settlement_status_label"], "待沉淀")
            self.assertIn("2026-05-19 微信反馈日报", payload["report"]["body_markdown"])
            self.assertTrue(payload["actions"]["copy_full_text"]["enabled"])
            self.assertFalse(payload["actions"]["confirm_settlement"]["enabled"])
            self.assertFalse(payload["safety"]["default_real_read_enabled"])

            human_text = json.dumps(
                {
                    "summary": payload["summary"],
                    "cards": payload["cards"],
                    "report": payload["report"],
                    "actions": payload["actions"],
                },
                ensure_ascii=False,
            )
            for token in [
                "workspace",
                "real_trial",
                "formal_path_not_configured",
                "real_read_disabled",
                "formal_write",
            ]:
                self.assertNotIn(token, human_text)

            text = json.dumps(payload, ensure_ascii=False)
            for forbidden in [
                "SECRET_BODY",
                "raw_payload_json",
                "content_text",
                "wxid_secret",
                "key",
                "salt",
                "daemon",
                str(root),
            ]:
                self.assertNotIn(forbidden, text)

    def test_daily_settlement_center_returns_date_rows_with_action_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(root)
            self._insert_candidate(conn, "D-001", "pending", "2026-05-19T09:00:00+08:00")
            self._insert_candidate(conn, "D-002", "confirmed", "2026-05-18T09:00:00+08:00")

            payload = daily_settlement_center_payload(config, conn)

            dates = [row["date"] for row in payload["items"]]
            self.assertIn("2026-05-19", dates)
            self.assertIn("2026-05-18", dates)
            first = next(row for row in payload["items"] if row["date"] == "2026-05-19")
            self.assertIn("monitor_group_count", first)
            self.assertIn("new_issue_count", first)
            self.assertIn("historical_unfollowed_count", first)
            self.assertIn("report_status_label", first)
            self.assertIn("settlement_status_label", first)
            self.assertIn("actions", first)
            self.assertIn("查看日报", first["actions"][0]["label"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("wxid_secret", text)

    def test_monitor_groups_crud_second_test_group_and_config_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = default_config(root)

            initial = monitor_groups_payload(config)
            second = next(
                group for group in initial["groups"] if group["group_name"] == "洽姐x稿定电商"
            )
            self.assertEqual(second["verification_label"], "待验证")
            self.assertFalse(second["include_in_daily"])
            self.assertFalse(second["counts_in_daily_center"])

    def test_load_config_adds_second_test_group_to_legacy_local_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config" / "app.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                """
app:
  host: "127.0.0.1"
  port: 8765
wx_cli:
  real_read_enabled: false
sessions:
  - external_id: "legacy-only"
    display_name: "旧配置监控群"
    is_whitelisted: true
    enabled: true
""".strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(config_path, root=root)
            payload = monitor_groups_payload(config)

            second = next(
                group for group in payload["groups"] if group["group_name"] == "洽姐x稿定电商"
            )
            self.assertEqual(second["verification_label"], "待验证")
            self.assertFalse(second["include_in_daily"])
            self.assertFalse(second["counts_in_daily_center"])

            created = save_monitor_group_payload(
                config,
                {
                    "group_name": "本地新增测试群",
                    "enabled": True,
                    "verification_status": "pending_verification",
                    "daily_monitor_enabled": True,
                    "include_in_daily": False,
                    "group_type": "测试群",
                    "module_name": "售后",
                    "customer_stage": "试读验证",
                    "owner_name": "负责人C",
                    "common_contacts": ["客户联系人C"],
                    "internal_people": ["负责人C", "我方同事"],
                    "trial_scope": "最近50条",
                    "reply_notes": "先内部确认再回复",
                    "is_whitelisted": True,
                    "real_read_enabled": True,
                },
            )
            group_id = created["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id)
            self.assertEqual(detail["group"]["group_name"], "本地新增测试群")
            self.assertEqual(detail["group"]["trial_scope"], "最近50条")
            self.assertEqual(detail["group"]["reply_notes"], "先内部确认再回复")
            self.assertEqual(detail["group"]["internal_people"], ["负责人C", "我方同事"])
            self.assertFalse(detail["group"]["include_in_daily"])
            self.assertFalse(config.wx_cli.real_read_enabled)

            updated = save_monitor_group_payload(
                config,
                {
                    "group_name": "本地新增测试群",
                    "enabled": True,
                    "verification_status": "verified",
                    "daily_monitor_enabled": True,
                    "include_in_daily": True,
                    "group_type": "客户群",
                    "module_name": "售后",
                    "customer_stage": "交付期",
                    "owner_name": "负责人C",
                    "common_contacts": ["客户联系人C"],
                    "internal_people": ["负责人C"],
                    "trial_scope": "最近50条",
                    "reply_notes": "已验证后纳入日报",
                },
                group_id=group_id,
            )
            self.assertTrue(updated["group"]["counts_in_daily_center"])
            self.assertEqual(monitor_groups_payload(config)["daily_center_count"], 2)

            disabled = disable_monitor_group_payload(config, group_id)
            self.assertEqual(disabled["status"], "disabled")
            self.assertFalse(disabled["group"]["enabled"])
            self.assertEqual(monitor_groups_payload(config)["daily_center_count"], 1)

            saved_text = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("real_read_enabled: false", saved_text)
            self.assertNotIn("real_read_enabled: true", saved_text)
            text = json.dumps(monitor_groups_payload(config), ensure_ascii=False)
            for forbidden in [
                "采集会话白名单",
                "is_whitelisted",
                "external_id",
                "wxid",
                "key",
                "salt",
                "daemon",
                str(root),
            ]:
                self.assertNotIn(forbidden, text)

    def test_candidate_resolution_status_payload_maps_home_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(root)
            pending_id = self._insert_candidate(
                conn, "P-001", "pending", "2026-05-19T09:00:00+08:00"
            )
            confirmed_id = self._insert_candidate(
                conn, "C-001", "confirmed", "2026-05-19T10:00:00+08:00"
            )
            rejected_id = self._insert_candidate(
                conn, "R-001", "rejected", "2026-05-19T11:00:00+08:00"
            )
            conn.execute(
                """
                insert into settlement_drafts (draft_date, file_path, item_ids_json, summary_json)
                values ('2026-05-19', ?, ?, '{}')
                """,
                (
                    str(root / "exports" / "draft.md"),
                    json.dumps([confirmed_id], ensure_ascii=False),
                ),
            )
            conn.commit()

            payload = candidate_resolution_status_payload(config, conn, "2026-05-19")

            self.assertEqual(
                [item["label"] for item in payload["available_statuses"]],
                ["待确认", "已确认跟进", "已忽略", "已写入日报", "已收口"],
            )
            labels_by_id = {
                item["item_id"]: item["home_status_label"] for item in payload["items"]
            }
            self.assertEqual(labels_by_id[pending_id], "待确认")
            self.assertEqual(labels_by_id[confirmed_id], "已写入日报")
            self.assertEqual(labels_by_id[rejected_id], "已忽略")
            self.assertFalse(payload["safety"]["formal_write_enabled"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def _setup_db(
        self, root: Path, sessions: list[SessionConfig] | None = None
    ) -> tuple[AppConfig, sqlite3.Connection]:
        config = AppConfig(
            root=root,
            wx_cli=WxCliConfig(real_read_enabled=False),
            sessions=sessions or [],
        )
        db_path = root / "data" / "test.sqlite3"
        conn = connect(db_path)
        init_db(conn)
        return config, conn

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
                    '本地客户', '', '订单', ?, ?,
                    'manual', ?, ?, ?)
            """,
            (
                item_code,
                status,
                f"{item_code} 待处理事项",
                f"{item_code} 安全摘要 wxid_secret_marker",
                f"agg-{item_code}",
                first_seen_at,
                first_seen_at,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


if __name__ == "__main__":
    unittest.main()
