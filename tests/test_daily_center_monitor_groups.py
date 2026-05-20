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
    config_center_payload,
    customer_options_api_payload,
    daily_center_payload,
    daily_settlement_center_payload,
    disable_monitor_group_payload,
    monitor_group_customer_suggestion_payload,
    monitor_group_detail_payload,
    monitor_groups_payload,
    refresh_monitor_group_members_payload,
    save_monitor_group_payload,
    sync_monitor_group_roster_payload,
)
from wechat_feedback_app.wx_cli_adapter import WxCliCommandResult


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
                        "pending-included",
                        "待验证纳入开关群",
                        module_name="售后",
                        owner_name="负责人待验证",
                        verification_status="pending_verification",
                        daily_monitor_enabled=True,
                        include_in_daily=True,
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

            groups_payload = monitor_groups_payload(config)
            pending_group = next(
                group
                for group in groups_payload["groups"]
                if group["group_name"] == "待验证纳入开关群"
            )
            self.assertFalse(pending_group["counts_in_daily_center"])
            self.assertEqual(groups_payload["daily_center_count"], 1)

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

    def test_pending_second_test_group_never_counts_even_when_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = default_config(root)
            conn = connect(root / "data" / "test.sqlite3")
            init_db(conn)
            second = next(
                session
                for session in config.sessions
                if session.display_name == "洽姐x稿定电商"
            )
            second.enabled = True
            second.daily_monitor_enabled = True
            second.include_in_daily = True
            second.verification_status = "pending_verification"
            expected_count = len(
                [
                    session
                    for session in config.sessions
                    if session.enabled
                    and session.daily_monitor_enabled
                    and session.include_in_daily
                    and session.verification_status == "verified"
                ]
            )

            groups_payload = monitor_groups_payload(config)
            second_payload = next(
                group
                for group in groups_payload["groups"]
                if group["group_name"] == "洽姐x稿定电商"
            )
            daily_payload = daily_center_payload(config, conn, "2026-05-19")

            self.assertEqual(second_payload["verification_label"], "待验证")
            self.assertTrue(second_payload["include_in_daily"])
            self.assertFalse(second_payload["counts_in_daily_center"])
            self.assertEqual(groups_payload["daily_center_count"], expected_count)
            self.assertEqual(
                daily_payload["summary"]["monitor_group_count"], expected_count
            )

    def test_monitor_group_detail_returns_local_member_options_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "member-group",
                        "成员选项测试群",
                        module_name="售后",
                        owner_name="负责人甲",
                        common_contacts=["客户联系人甲"],
                        internal_people=["我方人员甲"],
                    )
                ],
            )
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]
            self._insert_raw_message_member(conn, "member-group", "成员选项测试群", "成员甲")
            self._insert_raw_message_member(conn, "member-group", "成员选项测试群", "成员乙")
            self._insert_raw_message_member(
                conn, "member-group", "成员选项测试群", "成员选项测试群"
            )
            self._insert_raw_message_member(
                conn, "member-group", "成员选项测试群", "member-group"
            )
            self._insert_raw_message_member(
                conn, "member-group", "成员选项测试群", "wxid_marker_member"
            )
            self._insert_raw_message_member(
                conn, "member-group", "成员选项测试群", "key_marker_member"
            )
            self._insert_raw_message_member(
                conn, "member-group", "成员选项测试群", str(root / "secret.db")
            )

            payload = monitor_group_detail_payload(config, group_id, conn)
            options = payload["member_options"]
            names = payload["member_name_options"]

            self.assertFalse(options["complete"])
            self.assertEqual(options["scope"], "appeared_members")
            self.assertEqual(options["source_label"], "本地已出现成员（不是全员名单）")
            self.assertEqual(options["available_count"], len(names))
            self.assertEqual(options["appeared_count"], len(names))
            self.assertEqual(options["roster_count"], 0)
            self.assertIsNone(options["expected_count"])
            self.assertEqual(options["roster_members"], [])
            self.assertEqual(options["full_members"], [])
            self.assertEqual(options["refresh_label"], "刷新本地已出现成员")
            self.assertEqual(options["refresh_status"], "local_rebuilt")
            self.assertFalse(options["full_sync_available"])
            self.assertEqual(options["roster_status"], "real_mode_required")
            self.assertFalse(options["roster_refresh_available"])
            self.assertIn("不是微信群全员名单", options["status_label"])
            self.assertEqual(options["role_field_targets"]["group_owner"], "owner_names")
            self.assertEqual(options["role_labels"]["common_contact"], "常用联系人")
            for name in ["成员甲", "成员乙", "负责人甲", "客户联系人甲", "我方人员甲"]:
                self.assertIn(name, names)
            self.assertNotIn("成员选项测试群", names)
            self.assertNotIn("member-group", names)
            self.assertEqual(payload["group"]["member_name_options"], names)
            self.assertEqual(payload["group"]["member_options"]["count"], len(names))
            items_by_name = {
                item["value"]: item for item in payload["group"]["member_options"]["items"]
            }
            self.assertEqual(set(items_by_name), set(names))
            self.assertTrue(
                items_by_name["负责人甲"]["role_flags"]["group_owner"]
            )
            self.assertTrue(
                items_by_name["客户联系人甲"]["role_flags"]["common_contact"]
            )
            self.assertTrue(
                items_by_name["我方人员甲"]["role_flags"]["internal_person"]
            )
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_config_center_sessions_include_member_options_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "config-member-group",
                        "配置中心成员群",
                        module_name="售后",
                        owner_name="负责人甲",
                        common_contacts=["客户联系人甲"],
                        internal_people=["我方人员甲"],
                    )
                ],
            )
            self._insert_raw_message_member(conn, "config-member-group", "配置中心成员群", "成员甲")
            self._insert_raw_message_member(
                conn, "config-member-group", "配置中心成员群", "wxid_marker_member"
            )

            payload = config_center_payload(config, conn)
            session_payload = payload["editable"]["sessions"][0]

            self.assertIn("member_options", session_payload)
            self.assertIn("member_name_options", session_payload)
            self.assertFalse(session_payload["member_options"]["complete"])
            self.assertEqual(session_payload["member_options"]["refresh_status"], "local_rebuilt")
            self.assertEqual(session_payload["member_options"]["scope"], "appeared_members")
            self.assertFalse(session_payload["member_options"]["full_sync_available"])
            self.assertEqual(
                session_payload["member_options"]["roster_status"],
                "real_mode_required",
            )
            self.assertIn("成员甲", session_payload["member_name_options"])
            self.assertIn("负责人甲", session_payload["member_name_options"])
            self._assert_payload_has_no_sensitive_text(session_payload, root)

    def test_member_options_include_latest_trial_senders_when_main_db_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "monitor-group",
                        "当前监控群",
                        module_name="售后",
                    )
                ],
            )
            self._write_trial_member_db(
                root,
                ["本地试读成员甲", "wxid_marker_member", "key_marker_member", str(root / "secret.db")],
            )
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            detail = monitor_group_detail_payload(config, group_id, conn)
            config_payload = config_center_payload(config, conn)
            session_payload = config_payload["editable"]["sessions"][0]

            self.assertFalse(detail["member_options"]["complete"])
            self.assertEqual(
                detail["member_options"]["source_label"],
                "本地已出现成员（不是全员名单）",
            )
            self.assertEqual(detail["member_options"]["scope"], "appeared_members")
            self.assertEqual(detail["member_options"]["roster_count"], 0)
            self.assertIsNone(detail["member_options"]["expected_count"])
            self.assertEqual(detail["member_options"]["refresh_status"], "local_rebuilt")
            self.assertIn("不是微信群全员名单", detail["member_options"]["status_label"])
            self.assertIn("本地试读成员甲", detail["member_name_options"])
            self.assertEqual(session_payload["member_name_options"], detail["member_name_options"])
            self.assertGreater(len(session_payload["member_name_options"]), 0)
            self._assert_payload_has_no_sensitive_text(detail, root)
            self._assert_payload_has_no_sensitive_text(session_payload, root)

    def test_refresh_members_rebuilds_local_options_without_real_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "refresh-group",
                        "刷新成员群",
                        module_name="售后",
                    )
                ],
            )
            self._write_trial_member_db(root, ["刷新成员甲", "wxid_marker_member"])
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            payload = refresh_monitor_group_members_payload(config, group_id, conn)

            self.assertEqual(payload["status"], "refreshed")
            self.assertEqual(payload["refresh_label"], "刷新本地已出现成员")
            self.assertEqual(payload["refresh_status"], "local_rebuilt")
            self.assertGreater(payload["member_count"], 0)
            self.assertEqual(payload["scope"], "appeared_members")
            self.assertEqual(payload["available_count"], payload["member_count"])
            self.assertEqual(payload["appeared_count"], payload["member_count"])
            self.assertEqual(payload["roster_count"], 0)
            self.assertIsNone(payload["expected_count"])
            self.assertEqual(payload["roster_status"], "real_mode_required")
            self.assertFalse(payload["member_options"]["complete"])
            self.assertFalse(payload["full_sync_available"])
            self.assertTrue(payload["safety"]["no_real_read_executed"])
            self.assertIn("刷新成员甲", payload["member_name_options"])
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_roster_sync_contract_requires_authorization_before_real_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "roster-auth-group",
                        "全员同步授权群",
                        module_name="售后",
                    )
                ],
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]
            called = False

            def runner(_config, _args):
                nonlocal called
                called = True
                return WxCliCommandResult(
                    status="ok",
                    message="",
                    command="members --json",
                    parsed={"members": [{"display": "不应读取成员"}]},
                )

            payload = sync_monitor_group_roster_payload(
                config,
                group_id,
                {},
                conn,
                runner=runner,
            )

            self.assertEqual(payload["status"], "authorization_required")
            self.assertFalse(called)
            self.assertNotIn("member_name_options", payload)
            self.assertTrue(payload["full_sync_available"])
            self.assertTrue(payload["full_sync_requires_authorization"])
            self.assertEqual(payload["roster_status"], "authorization_required")
            self.assertEqual(payload["roster_count"], 0)
            for forbidden_key in [
                "names",
                "items",
                "appeared_members",
                "full_members",
                "roster_members",
            ]:
                self.assertNotIn(forbidden_key, payload["member_options"])
            self.assertNotIn("不应读取成员", json.dumps(payload, ensure_ascii=False))
            self.assertTrue(payload["safety"]["no_roster_read_executed"])
            self.assertTrue(payload["safety"]["no_message_read_executed"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_roster_sync_failure_returns_blocked_without_member_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "roster-failure-group",
                        "全员同步失败群",
                        module_name="售后",
                    )
                ],
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )
            self._insert_raw_message_member(
                conn, "roster-failure-group", "全员同步失败群", "本地兜底甲"
            )
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            def runner(_config, _args):
                return WxCliCommandResult(
                    status="parse_error",
                    message="",
                    command="members --json",
                )

            payload = sync_monitor_group_roster_payload(
                config,
                group_id,
                {"authorize_full_roster_sync": True},
                conn,
                runner=runner,
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["error_code"], "parse_error")
            self.assertEqual(payload["scope"], "appeared_members")
            self.assertGreater(payload["available_count"], 0)
            self.assertEqual(payload["roster_count"], 0)
            self.assertNotIn("member_name_options", payload)
            for forbidden_key in [
                "names",
                "items",
                "appeared_members",
                "full_members",
                "roster_members",
            ]:
                self.assertNotIn(forbidden_key, payload["member_options"])
            payload_text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("本地兜底甲", payload_text)
            self.assertFalse(config.wx_cli.real_read_enabled)
            self.assertTrue(payload["safety"]["no_message_read_executed"])
            self.assertFalse(payload["safety"]["save_triggers_collection"])
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_roster_sync_stub_returns_full_member_scope_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "roster-stub-group",
                        "全员同步桩群",
                        module_name="售后",
                        owner_name="全员甲",
                    )
                ],
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )
            self._insert_raw_message_member(conn, "roster-stub-group", "全员同步桩群", "本地出现甲")
            group_id = monitor_groups_payload(config)["groups"][0]["group_id"]

            def runner(_config, args):
                self.assertEqual(args, ["members", "全员同步桩群", "--json"])
                return WxCliCommandResult(
                    status="ok",
                    message="",
                    command="members --json",
                    parsed={
                        "members": [
                            {"display": "全员甲", "is_owner": True},
                            {"nickname": "全员乙"},
                            {"display": "wxid_marker_member"},
                            {"display": str(root / "secret.db")},
                        ]
                    },
                )

            payload = sync_monitor_group_roster_payload(
                config,
                group_id,
                {"authorize_full_roster_sync": True},
                conn,
                runner=runner,
            )
            options = payload["member_options"]

            self.assertEqual(payload["status"], "synced")
            self.assertEqual(options["scope"], "roster_members")
            self.assertTrue(options["complete"])
            self.assertEqual(options["source_label"], "微信群全员名单")
            self.assertEqual(options["roster_count"], 2)
            self.assertEqual(options["expected_count"], 2)
            self.assertEqual(options["available_count"], 2)
            self.assertGreaterEqual(options["appeared_count"], 1)
            self.assertEqual(options["roster_status"], "synced")
            self.assertTrue(options["full_sync_available"])
            self.assertTrue(options["full_sync_requires_authorization"])
            self.assertEqual(payload["member_name_options"], ["全员甲", "全员乙"])
            self.assertEqual(options["full_members"], ["全员甲", "全员乙"])
            self.assertEqual(options["roster_members"], ["全员甲", "全员乙"])
            self.assertIn("本地出现甲", options["appeared_members"])
            self.assertTrue(options["items"][0]["role_flags"]["group_owner"])
            self.assertFalse(payload["safety"]["no_roster_read_executed"])
            self.assertTrue(payload["safety"]["no_message_read_executed"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_create_monitor_group_can_authorize_initial_roster_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )
            called = False

            def runner(_config, args):
                nonlocal called
                called = True
                self.assertEqual(args, ["members", "新增全员群", "--json"])
                return WxCliCommandResult(
                    status="ok",
                    message="",
                    command="members --json",
                    parsed={
                        "members": [
                            {"display": "全员甲"},
                            {"display": "全员乙"},
                            {"display": "wxid_marker_member"},
                        ]
                    },
                )

            payload = save_monitor_group_payload(
                config,
                {
                    "group_name": "新增全员群",
                    "verification_status": "pending_verification",
                    "include_in_daily": False,
                    "authorize_full_roster_sync_on_create": True,
                },
                conn=conn,
                roster_runner=runner,
            )
            group_id = payload["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id, conn)

            self.assertTrue(called)
            self.assertEqual(payload["status"], "saved")
            self.assertEqual(payload["initial_roster_sync"]["status"], "synced")
            self.assertEqual(payload["initial_roster_sync"]["scope"], "roster_members")
            self.assertTrue(payload["initial_roster_sync"]["complete"])
            self.assertEqual(payload["initial_roster_sync"]["roster_count"], 2)
            self.assertEqual(payload["member_options"]["scope"], "roster_members")
            self.assertTrue(payload["member_options"]["complete"])
            self.assertEqual(payload["member_options"]["roster_count"], 2)
            self.assertEqual(detail["member_options"]["scope"], "roster_members")
            self.assertTrue(detail["member_options"]["complete"])
            self.assertEqual(detail["member_options"]["roster_count"], 2)
            saved_text = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("roster_member_names:", saved_text)
            self.assertIn("real_read_enabled: false", saved_text)
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(payload, root)
            self._assert_payload_has_no_sensitive_text(detail, root)

    def test_create_monitor_group_without_initial_roster_authorization_does_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )
            called = False

            def runner(_config, _args):
                nonlocal called
                called = True
                return WxCliCommandResult(
                    status="ok",
                    message="",
                    command="members --json",
                    parsed={"members": [{"display": "不应同步"}]},
                )

            payload = save_monitor_group_payload(
                config,
                {
                    "group_name": "未授权新增群",
                    "verification_status": "pending_verification",
                    "include_in_daily": False,
                    "authorize_full_roster_sync_on_create": False,
                },
                conn=conn,
                roster_runner=runner,
            )

            self.assertFalse(called)
            self.assertEqual(payload["status"], "saved")
            self.assertEqual(payload["initial_roster_sync"]["status"], "authorization_required")
            self.assertTrue(payload["initial_roster_sync"]["safety"]["no_roster_read_executed"])
            self.assertEqual(payload["member_options"]["scope"], "appeared_members")
            self.assertFalse(payload["member_options"]["complete"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self.assertNotIn("不应同步", json.dumps(payload, ensure_ascii=False))
            self._assert_payload_has_no_sensitive_text(payload, root)

    def test_create_monitor_group_initial_roster_failure_does_not_block_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                wx_cli=WxCliConfig(
                    mode="real",
                    binary="/bin/echo",
                    real_read_enabled=False,
                ),
            )

            def runner(_config, _args):
                return WxCliCommandResult(
                    status="parse_error",
                    message="",
                    command="members --json",
                )

            payload = save_monitor_group_payload(
                config,
                {
                    "group_name": "同步失败新增群",
                    "verification_status": "pending_verification",
                    "include_in_daily": False,
                    "authorize_full_roster_sync_on_create": True,
                },
                conn=conn,
                roster_runner=runner,
            )
            group_id = payload["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id, conn)

            self.assertEqual(payload["status"], "saved")
            self.assertEqual(payload["initial_roster_sync"]["status"], "blocked")
            self.assertEqual(payload["initial_roster_sync"]["error_code"], "parse_error")
            self.assertEqual(payload["initial_roster_sync"]["roster_count"], 0)
            self.assertEqual(detail["status"], "ok")
            self.assertEqual(detail["member_options"]["scope"], "appeared_members")
            self.assertFalse(detail["member_options"]["complete"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(payload, root)
            self._assert_payload_has_no_sensitive_text(detail, root)

    def test_monitor_group_legacy_strings_read_as_arrays(self):
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
  - external_id: "legacy-member-group"
    display_name: "旧成员配置群"
    owner_name: "负责人甲,负责人乙"
    common_contacts: "客户联系人甲，客户联系人乙"
    internal_people: "我方人员甲\\n我方人员乙"
    is_whitelisted: true
    enabled: true
""".strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(config_path, root=root)
            group_id = next(
                group["group_id"]
                for group in monitor_groups_payload(config)["groups"]
                if group["group_name"] == "旧成员配置群"
            )
            detail = monitor_group_detail_payload(config, group_id)

            self.assertEqual(detail["group"]["owner_name"], "负责人甲")
            self.assertEqual(detail["group"]["owner_names"], ["负责人甲", "负责人乙"])
            self.assertEqual(
                detail["group"]["common_contacts"], ["客户联系人甲", "客户联系人乙"]
            )
            self.assertEqual(detail["group"]["internal_people"], ["我方人员甲", "我方人员乙"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(detail, root)

    def test_monitor_group_multi_select_save_persists_arrays_without_real_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(root)
            created = save_monitor_group_payload(
                config,
                {
                    "group_name": "多选保存测试群",
                    "enabled": True,
                    "verification_status": "pending_verification",
                    "daily_monitor_enabled": True,
                    "include_in_daily": False,
                    "group_type": "测试群",
                    "module_name": "售后",
                    "customer_stage": "试读验证",
                    "owner_names": ["负责人甲", "负责人乙"],
                    "common_contacts": ["客户联系人甲", "客户联系人乙"],
                    "internal_people": ["我方人员甲", "我方人员乙"],
                    "trial_scope": "最近50条",
                    "reply_notes": "仅保存配置",
                    "real_read_enabled": True,
                },
                conn=conn,
            )
            group_id = created["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id, conn)

            self.assertEqual(detail["group"]["owner_name"], "负责人甲")
            self.assertEqual(detail["group"]["owner_names"], ["负责人甲", "负责人乙"])
            self.assertEqual(
                detail["group"]["common_contacts"], ["客户联系人甲", "客户联系人乙"]
            )
            self.assertEqual(detail["group"]["internal_people"], ["我方人员甲", "我方人员乙"])
            self.assertFalse(config.wx_cli.real_read_enabled)

            saved_text = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("owner_names:", saved_text)
            self.assertIn("real_read_enabled: false", saved_text)
            self.assertNotIn("real_read_enabled: true", saved_text)
            self._assert_payload_has_no_sensitive_text(detail, root)

    def test_customer_options_include_configured_sessions_and_config_center_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("session-a", "客户A项目群", customer_name="客户A"),
                    SessionConfig("session-b", "客户B项目群", customer_name="客户B"),
                    SessionConfig("session-c", "未标客户群"),
                ],
            )

            monitor_payload = monitor_groups_payload(config)
            config_payload = config_center_payload(config, conn)

            self.assertEqual(monitor_payload["customer_options_count"], 2)
            self.assertEqual(config_payload["customer_options_count"], 2)
            self.assertEqual(config_payload["editable"]["customer_options_count"], 2)
            self.assertEqual(
                config_payload["editable"]["sessions"][0]["customer_options_count"], 2
            )
            self.assertEqual(
                config_payload["editable"]["sessions"][0]["customer_suggestion"][
                    "match_status"
                ],
                "matched",
            )
            options_payload = customer_options_api_payload(config)
            self.assertEqual(options_payload["status"], "ok")
            self.assertEqual(options_payload["count"], 2)
            self.assertEqual(options_payload["customer_options_count"], 2)
            self.assertEqual(len(options_payload["options"]), 2)
            self.assertEqual(len(options_payload["customer_options"]), 2)
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(monitor_payload, root)
            self._assert_payload_has_no_sensitive_text(options_payload, root)

    def test_customer_suggestion_endpoint_contract_matches_group_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("session-a", "历史客户群", customer_name="客户A"),
                ],
            )

            matched = monitor_group_customer_suggestion_payload(config, "客户A售后跟进群")
            unmatched = monitor_group_customer_suggestion_payload(config, "陌生售后群")

            self.assertEqual(matched["status"], "ok")
            self.assertEqual(matched["match_status"], "matched")
            self.assertEqual(matched["reason_code"], "substring_match")
            self.assertTrue(matched["suggested_customer_id"])
            self.assertEqual(unmatched["match_status"], "needs_manual_selection")
            self.assertEqual(unmatched["reason_code"], "no_reliable_match")
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(matched, root)

    def test_customer_suggestion_ignores_channel_brackets_and_group_suffix_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig(
                        "session-a",
                        "历史客户群",
                        customer_name="甲方X稿定电商",
                    ),
                ],
            )

            matched = monitor_group_customer_suggestion_payload(
                config,
                "甲方 稿定电商（小红书）售后群",
            )

            self.assertEqual(matched["status"], "ok")
            self.assertEqual(matched["customer_options_count"], 1)
            self.assertEqual(matched["match_status"], "matched")
            self.assertIn(matched["reason_code"], {"normalized_match", "substring_match"})
            self.assertTrue(matched["suggested_customer_id"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(matched, root)

    def test_customer_options_merge_strawberry_customer_system_source_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("local-a", "本地客户群", customer_name="本地客户"),
                ],
            )

            options_payload = customer_options_api_payload(
                config,
                strawberry_loader=lambda: [
                    {"name": "本地客户"},
                    {"name": "客户系统A"},
                ],
            )

            self.assertEqual(options_payload["status"], "ok")
            self.assertEqual(options_payload["source_status"], "ok")
            self.assertEqual(options_payload["source_error_code"], "")
            self.assertEqual(options_payload["customer_options_count"], 2)
            local_option = next(
                option
                for option in options_payload["customer_options"]
                if option["customer_name"] == "本地客户"
            )
            self.assertIn("local_config", local_option["sources"])
            self.assertIn("strawberry_customer_system", local_option["sources"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(options_payload, root)

    def test_customer_suggestion_matches_strawberry_customer_system_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _conn = self._setup_db(root)

            matched = monitor_group_customer_suggestion_payload(
                config,
                "客户系统A X稿定电商（小红书）售后群",
                strawberry_loader=lambda: [{"name": "客户系统A"}],
            )

            self.assertEqual(matched["status"], "ok")
            self.assertEqual(matched["customer_source_status"], "ok")
            self.assertEqual(matched["customer_options_count"], 1)
            self.assertEqual(matched["match_status"], "matched")
            self.assertTrue(matched["suggested_customer_id"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(matched, root)

    def test_customer_options_source_unavailable_returns_clear_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("local-a", "本地客户群", customer_name="本地客户"),
                ],
            )

            def missing_source() -> list[object]:
                raise FileNotFoundError("missing")

            options_payload = customer_options_api_payload(
                config,
                strawberry_loader=missing_source,
            )

            self.assertEqual(options_payload["status"], "ok")
            self.assertEqual(options_payload["source_status"], "partial")
            self.assertEqual(options_payload["source_error_code"], "source_path_missing")
            self.assertEqual(options_payload["customer_options_count"], 1)
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(options_payload, root)

    def test_new_monitor_group_suggests_customer_from_group_name_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("existing-a", "历史客户群", customer_name="客户A"),
                ],
            )

            created = save_monitor_group_payload(
                config,
                {
                    "group_name": "客户A售后跟进群",
                    "enabled": True,
                    "verification_status": "pending_verification",
                    "daily_monitor_enabled": True,
                    "include_in_daily": False,
                    "group_type": "客户群",
                    "module_name": "售后",
                    "customer_stage": "试读验证",
                    "real_read_enabled": True,
                },
                conn=conn,
            )
            group_id = created["group"]["group_id"]
            detail = monitor_group_detail_payload(config, group_id, conn)

            self.assertEqual(created["customer_suggestion"]["match_status"], "matched")
            self.assertEqual(created["customer_suggestion"]["reason_code"], "substring_match")
            self.assertEqual(created["group"]["customer_name"], "客户A")
            self.assertTrue(created["group"]["customer_id"])
            self.assertEqual(detail["group"]["customer_name"], "客户A")
            self.assertEqual(detail["group"]["customer_id"], created["group"]["customer_id"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(created, root)

    def test_new_monitor_group_unknown_customer_needs_manual_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(
                root,
                sessions=[
                    SessionConfig("existing-a", "历史客户群", customer_name="客户A"),
                ],
            )

            created = save_monitor_group_payload(
                config,
                {
                    "group_name": "陌生售后跟进群",
                    "enabled": True,
                    "verification_status": "pending_verification",
                    "daily_monitor_enabled": True,
                    "include_in_daily": False,
                    "group_type": "客户群",
                    "module_name": "售后",
                    "customer_stage": "试读验证",
                },
                conn=conn,
            )

            self.assertEqual(
                created["customer_suggestion"]["match_status"],
                "needs_manual_selection",
            )
            self.assertEqual(created["customer_suggestion"]["reason_code"], "no_reliable_match")
            self.assertEqual(created["group"]["customer_name"], "")
            self.assertEqual(created["group"]["customer_id"], "")
            self.assertFalse(config.wx_cli.real_read_enabled)
            self._assert_payload_has_no_sensitive_text(created, root)

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

    def _insert_raw_message_member(
        self, conn: sqlite3.Connection, external_id: str, display_name: str, member_name: str
    ) -> None:
        row = conn.execute(
            "select id from sessions where external_id = ?", (external_id,)
        ).fetchone()
        if row is None:
            cursor = conn.execute(
                "insert into sessions (external_id, display_name) values (?, ?)",
                (external_id, display_name),
            )
            session_id = int(cursor.lastrowid)
        else:
            session_id = int(row["id"])
        run_row = conn.execute("select id from collection_runs limit 1").fetchone()
        if run_row is None:
            cursor = conn.execute(
                """
                insert into collection_runs (
                  mode, started_at, finished_at, status, raw_messages_seen,
                  raw_messages_inserted, raw_messages_duplicated,
                  candidate_items_created
                )
                values (
                  'fixture', '2026-05-19T09:00:00+08:00',
                  '2026-05-19T09:01:00+08:00', 'success', 0, 0, 0, 0
                )
                """
            )
            run_id = int(cursor.lastrowid)
        else:
            run_id = int(run_row["id"])
        safe_key = f"{external_id}-{member_name}"
        conn.execute(
            """
            insert into raw_messages (
              session_id, sender_display_name, sender_role, sent_at, message_type,
              content_text, content_hash, dedupe_key, raw_payload_json,
              collection_run_id
            )
            values (?, ?, 'customer', '2026-05-19T09:00:00+08:00', 'text',
                    'fixture body', ?, ?, '{}', ?)
            """,
            (session_id, member_name, f"hash-{safe_key}", f"dedupe-{safe_key}", run_id),
        )
        conn.commit()

    def _write_trial_member_db(self, root: Path, member_names: list[str]) -> None:
        db_path = root / "data" / "real_trial_recent50_20260519-160000.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """
            insert into sessions (id, external_id, display_name)
            values (1, 'trial-session', '试读群')
            """
        )
        conn.execute(
            """
            insert into collection_runs (
              id, mode, started_at, finished_at, status, raw_messages_seen,
              raw_messages_inserted, raw_messages_duplicated,
              candidate_items_created
            )
            values (
              1, 'real', '2026-05-19T09:00:00+08:00',
              '2026-05-19T09:01:00+08:00', 'success', ?, ?, 0, 0
            )
            """,
            (len(member_names), len(member_names)),
        )
        for index, member_name in enumerate(member_names, start=1):
            conn.execute(
                """
                insert into raw_messages (
                  id, session_id, sender_display_name, sender_role, sent_at,
                  message_type, content_text, content_hash, dedupe_key,
                  raw_payload_json, collection_run_id
                )
                values (?, 1, ?, 'customer', '2026-05-19T09:00:00+08:00',
                        'text', 'fixture body', ?, ?, '{}', 1)
                """,
                (index, member_name, f"trial-hash-{index}", f"trial-dedupe-{index}"),
            )
        conn.commit()
        conn.close()

    def _assert_payload_has_no_sensitive_text(self, payload: object, root: Path) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for forbidden in [
            "wxid",
            "key",
            "salt",
            "daemon",
            str(root),
        ]:
            self.assertNotIn(forbidden, text)

    def _setup_db(
        self,
        root: Path,
        sessions: list[SessionConfig] | None = None,
        wx_cli: WxCliConfig | None = None,
    ) -> tuple[AppConfig, sqlite3.Connection]:
        config = AppConfig(
            root=root,
            wx_cli=wx_cli or WxCliConfig(real_read_enabled=False),
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
