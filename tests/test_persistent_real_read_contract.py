from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.collector import collect_normalized_messages
from wechat_feedback_app.config import AppConfig, SessionConfig, WxCliConfig
from wechat_feedback_app.db import setup_database
from wechat_feedback_app.routes import (
    config_center_payload,
    detected_wechat_group_sessions,
    monitor_groups_payload,
    persistent_real_read_control_payload,
    real_trial_run_plan,
    safe_config_payload,
    safe_status_payload,
    save_config_center_payload,
    upsert_detected_monitor_groups,
)
from wechat_feedback_app.wx_cli_adapter import NormalizedMessage


def sample_config(
    root: Path | None = None,
    *,
    enabled: bool = False,
    paused: bool = False,
    schedule_enabled: bool = False,
    max_lookback_days: float = 30,
) -> AppConfig:
    return AppConfig(
        root=root or Path("/tmp/wechat-feedback-persistent-real-read-test"),
        wx_cli=WxCliConfig(
            mode="real",
            real_read_enabled=False,
            expanded_real_lookback_days=max_lookback_days,
            expanded_real_max_groups=3,
            expanded_real_max_total_messages=900,
            expanded_real_max_messages_per_group=300,
            expanded_real_batch_limit=2,
            persistent_real_read_enabled=enabled,
            persistent_real_read_paused=paused,
            persistent_real_read_test_account_confirmed=enabled,
            persistent_real_read_schedule_enabled=schedule_enabled,
            persistent_real_read_interval_minutes=45,
            persistent_real_read_default_lookback_days=30,
        ),
        sessions=[
            SessionConfig("group-a", "测试群A", "客户A", enabled=True, is_whitelisted=True),
            SessionConfig("group-b", "测试群B", "客户B", enabled=True, is_whitelisted=True),
            SessionConfig("group-c", "测试群C", enabled=False, is_whitelisted=True),
            SessionConfig("group-d", "测试群D", enabled=True, is_whitelisted=False),
        ],
    )


def persistent_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "scope_mode": "configurable_window",
        "authorization_mode": "persistent",
        "trigger": "manual",
        "include_all_enabled_whitelist": True,
        "max_total_messages": 800,
        "max_messages_per_group": 250,
        "batch_limit": 1,
    }
    payload.update(overrides)
    return payload


def all_wechat_groups_payload(**overrides: object) -> dict[str, object]:
    return persistent_payload(
        scope_mode="all_wechat_groups",
        include_all_detected_groups=True,
        **overrides,
    )


def detected_session_probe_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "sessions": [
            {
                "id": "room-a@chatroom",
                "name": "探针群一",
                "type": "group",
                "is_group": True,
            },
            {
                "id": "room-b@chatroom",
                "display_name": "探针群二",
                "chat_type": "chatroom",
            },
            {
                "id": "single-a",
                "name": "单聊甲",
                "type": "single",
                "is_group": False,
            },
            {
                "id": "official-a",
                "name": "公众号甲",
                "type": "official",
            },
            {
                "id": "filehelper",
                "name": "文件传输助手",
                "type": "system",
            },
        ],
    }


def english_room_group_probe_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "sessions": [
            {
                "id": "single-showroom",
                "name": "Customer Showroom",
            },
            {
                "id": "single-workgroup",
                "display_name": "Marketing Group Updates",
            },
            {
                "id": "english-team@chatroom",
                "display_name": "Operations Group",
                "chat_type": "chatroom",
            },
        ],
    }


def readable_group_metadata_probe_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "sessions": [
            {
                "id": "123456789012345@chatroom",
                "group_name": "Readable Probe Group",
                "chat_type": "chatroom",
            }
        ],
    }


def nested_readable_group_metadata_probe_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "sessions": [
            {
                "id": "223456789012345@chatroom",
                "chat_type": "chatroom",
                "contact": {
                    "remarkName": "Nested Readable Probe Group",
                },
            }
        ],
    }


def internal_id_only_group_probe_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "sessions": [
            {
                "id": "123456789012345@chatroom",
                "chat_type": "chatroom",
            }
        ],
    }


def assert_no_sensitive_fields(testcase: unittest.TestCase, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    for forbidden in (
        "wxid",
        "salt",
        "daemon",
        "/private/",
        "真实消息",
        "候选正文",
        "测试群A",
        "测试群B",
        "探针群一",
        "探针群二",
        "单聊甲",
        "公众号甲",
        "Customer Showroom",
        "Marketing Group Updates",
        "Operations Group",
        "group-a",
        "group-b",
        "room-a",
        "room-b",
        "single-showroom",
        "single-workgroup",
        "english-team",
        "single-a",
        "official-a",
        "member_name_options",
        "raw_payload",
        '"key":',
    ):
        testcase.assertNotIn(forbidden, text)


def key_paths(value: object, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.append(child_prefix)
            paths.extend(key_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(key_paths(child, f"{prefix}[]"))
        return paths
    return []


class PersistentRealReadContractTest(unittest.TestCase):
    def test_persistent_mode_is_default_off_and_blocks_execution(self):
        config = sample_config(enabled=False)

        result = real_trial_run_plan(config, persistent_payload())

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "persistent_real_read_disabled")
        self.assertFalse(result["will_run"])
        self.assertTrue(result["execution"]["no_real_read_executed"])
        self.assertFalse(result["real_read_enabled_after"])
        assert_no_sensitive_fields(self, result)

    def test_enabled_persistent_mode_runs_manual_trigger_with_fake_executor(self):
        config = sample_config(enabled=True)

        def fake_executor(plan: dict) -> dict:
            self.assertEqual(plan["authorization_mode"], "persistent")
            self.assertEqual(plan["trigger"], "manual")
            self.assertEqual(plan["selected_group_count"], 2)
            self.assertEqual(plan["window"]["effective_lookback_days"], 30)
            return {
                "status": "success",
                "error_code": "",
                "sessions_total": 2,
                "sessions_success": 2,
                "sessions_failed": 0,
                "raw_messages_seen": 20,
                "raw_messages_inserted": 18,
                "raw_messages_duplicated": 2,
                "candidate_items_created": 5,
                "candidate_items_updated": 1,
            }

        result = real_trial_run_plan(
            config,
            persistent_payload(),
            executor=fake_executor,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["authorization_mode"], "persistent")
        self.assertTrue(result["will_run"])
        self.assertFalse(result["real_read_enabled_after"])
        self.assertEqual(result["execution_summary"]["raw_messages_inserted"], 18)
        self.assertEqual(result["execution_summary"]["candidate_items_created"], 5)
        self.assertFalse(config.wx_cli.real_read_enabled)
        assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_scope_uses_probe_groups_and_fake_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)

            def fake_executor(plan: dict) -> dict:
                self.assertEqual(plan["scope_mode"], "all_wechat_groups")
                self.assertEqual(plan["selected_group_count"], 2)
                self.assertEqual(plan["detected_session_count"], 5)
                self.assertEqual(plan["detected_group_count"], 2)
                self.assertEqual(plan["excluded_non_group_count"], 3)
                return {
                    "status": "success",
                    "sessions_total": plan["selected_group_count"],
                    "sessions_success": plan["selected_group_count"],
                    "raw_messages_seen": 8,
                    "raw_messages_inserted": 6,
                    "raw_messages_duplicated": 2,
                    "candidate_items_created": 2,
                }

            result = real_trial_run_plan(
                config,
                all_wechat_groups_payload(),
                executor=fake_executor,
                session_probe=lambda _config: detected_session_probe_payload(),
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["scope"]["scope_mode"], "all_wechat_groups")
            self.assertEqual(result["scope"]["selected_group_count"], 2)
            self.assertEqual(result["scope"]["detected_session_count"], 5)
            self.assertEqual(result["scope"]["detected_group_count"], 2)
            self.assertEqual(result["scope"]["excluded_non_group_count"], 3)
            self.assertGreaterEqual(result["scope"]["local_monitor_groups_upserted"], 0)
            self.assertFalse(result["scope"]["groups_returned"])
            self.assertFalse(result["scope"]["session_names_returned"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            saved = (Path(tmp) / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("detected-wechat-group-", saved)
            assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_excludes_non_group_sessions(self):
        config = sample_config(enabled=True)

        result = real_trial_run_plan(
            config,
            all_wechat_groups_payload(),
            executor=lambda plan: {
                "status": "success",
                "sessions_total": plan["selected_group_count"],
                "sessions_success": plan["selected_group_count"],
            },
            session_probe=lambda _config: detected_session_probe_payload(),
        )

        self.assertEqual(result["scope"]["selected_group_count"], 2)
        self.assertEqual(result["scope"]["excluded_non_group_count"], 3)
        self.assertEqual(result["scope"]["source_status"], "ok")
        assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_does_not_match_english_room_group_names(self):
        config = sample_config(enabled=True)

        def fake_executor(plan: dict) -> dict:
            self.assertEqual(plan["scope_mode"], "all_wechat_groups")
            self.assertEqual(plan["detected_session_count"], 3)
            self.assertEqual(plan["detected_group_count"], 1)
            self.assertEqual(plan["excluded_non_group_count"], 2)
            self.assertEqual(plan["selected_group_count"], 1)
            return {
                "status": "success",
                "sessions_total": plan["selected_group_count"],
                "sessions_success": plan["selected_group_count"],
            }

        result = real_trial_run_plan(
            config,
            all_wechat_groups_payload(),
            executor=fake_executor,
            session_probe=lambda _config: english_room_group_probe_payload(),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["scope"]["selected_group_count"], 1)
        self.assertEqual(result["scope"]["detected_group_count"], 1)
        self.assertEqual(result["scope"]["excluded_non_group_count"], 2)
        assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_uses_readable_metadata_as_saved_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)

            result = real_trial_run_plan(
                config,
                all_wechat_groups_payload(),
                executor=lambda plan: {
                    "status": "success",
                    "sessions_total": plan["selected_group_count"],
                    "sessions_success": plan["selected_group_count"],
                },
                session_probe=lambda _config: readable_group_metadata_probe_payload(),
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["scope"]["detected_group_count"], 1)
            detected = next(
                session
                for session in config.sessions
                if session.display_name == "Readable Probe Group"
            )
            self.assertEqual(detected.display_name_status, "resolved")
            self.assertEqual(detected.display_name_source, "group_name")
            public = next(
                group
                for group in monitor_groups_payload(config)["groups"]
                if group["group_name"] == "Readable Probe Group"
            )
            self.assertEqual(public["display_name_status"], "resolved")
            self.assertNotIn("@chatroom", json.dumps(public, ensure_ascii=False))
            assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_uses_nested_contact_metadata_as_saved_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)

            result = real_trial_run_plan(
                config,
                all_wechat_groups_payload(),
                executor=lambda plan: {
                    "status": "success",
                    "sessions_total": plan["selected_group_count"],
                    "sessions_success": plan["selected_group_count"],
                },
                session_probe=lambda _config: nested_readable_group_metadata_probe_payload(),
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["scope"]["detected_group_count"], 1)
            detected = next(
                session
                for session in config.sessions
                if session.display_name == "Nested Readable Probe Group"
            )
            self.assertEqual(detected.display_name_status, "resolved")
            self.assertEqual(detected.display_name_source, "contact.remarkName")
            public = next(
                group
                for group in monitor_groups_payload(config)["groups"]
                if group["group_name"] == "Nested Readable Probe Group"
            )
            self.assertEqual(public["display_name_status"], "resolved")
            self.assertNotIn("@chatroom", json.dumps(public, ensure_ascii=False))
            assert_no_sensitive_fields(self, result)

    def test_persistent_all_wechat_groups_marks_internal_id_only_display_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)

            result = real_trial_run_plan(
                config,
                all_wechat_groups_payload(),
                executor=lambda plan: {
                    "status": "success",
                    "sessions_total": plan["selected_group_count"],
                    "sessions_success": plan["selected_group_count"],
                },
                session_probe=lambda _config: internal_id_only_group_probe_payload(),
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["scope"]["detected_group_count"], 1)
            self.assertEqual(result["scope"]["unresolved_display_name_count"], 1)
            unresolved = next(
                session
                for session in config.sessions
                if session.display_name == "群名待解析"
            )
            self.assertEqual(unresolved.display_name_status, "unresolved")
            self.assertEqual(
                unresolved.display_name_reason_code, "internal_identifier_only"
            )
            public = next(
                group
                for group in monitor_groups_payload(config)["groups"]
                if group["group_name"] == "群名待解析"
            )
            self.assertEqual(public["display_name_status"], "unresolved")
            self.assertEqual(
                public["display_name_reason_code"], "internal_identifier_only"
            )
            self.assertNotIn(
                "123456789012345@chatroom",
                json.dumps(public, ensure_ascii=False),
            )
            assert_no_sensitive_fields(self, result)

    def test_unresolved_placeholder_does_not_merge_different_detected_groups_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)
            sessions_a, _summary_a = detected_wechat_group_sessions(
                {
                    "status": "ok",
                    "sessions": [
                        {"id": "100000000001@chatroom", "chat_type": "chatroom"}
                    ],
                }
            )
            sessions_b, _summary_b = detected_wechat_group_sessions(
                {
                    "status": "ok",
                    "sessions": [
                        {"id": "100000000002@chatroom", "chat_type": "chatroom"}
                    ],
                }
            )

            first_inserted = upsert_detected_monitor_groups(config, sessions_a)
            second_inserted = upsert_detected_monitor_groups(config, sessions_b)

            self.assertEqual(first_inserted, 1)
            self.assertEqual(second_inserted, 1)
            unresolved_count = len(
                [
                    session
                    for session in config.sessions
                    if session.display_name == "群名待解析"
                    and session.display_name_status == "unresolved"
                ]
            )
            self.assertEqual(unresolved_count, 2)

    def test_same_external_id_unresolved_group_can_upgrade_to_resolved_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)
            unresolved, _summary_unresolved = detected_wechat_group_sessions(
                {
                    "status": "ok",
                    "sessions": [
                        {"id": "100000000003@chatroom", "chat_type": "chatroom"}
                    ],
                }
            )
            resolved, _summary_resolved = detected_wechat_group_sessions(
                {
                    "status": "ok",
                    "sessions": [
                        {
                            "id": "100000000003@chatroom",
                            "group_name": "Readable Upgrade Group",
                            "chat_type": "chatroom",
                        }
                    ],
                }
            )

            self.assertEqual(upsert_detected_monitor_groups(config, unresolved), 1)
            self.assertEqual(upsert_detected_monitor_groups(config, resolved), 0)
            upgraded = next(
                session
                for session in config.sessions
                if session.display_name == "Readable Upgrade Group"
            )
            self.assertEqual(upgraded.display_name_status, "resolved")

    def test_same_external_id_unresolved_group_can_upgrade_from_nested_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)
            unresolved, _summary_unresolved = detected_wechat_group_sessions(
                {
                    "status": "ok",
                    "sessions": [
                        {"id": "223456789012345@chatroom", "chat_type": "chatroom"}
                    ],
                }
            )
            resolved, _summary_resolved = detected_wechat_group_sessions(
                nested_readable_group_metadata_probe_payload()
            )

            self.assertEqual(upsert_detected_monitor_groups(config, unresolved), 1)
            self.assertEqual(upsert_detected_monitor_groups(config, resolved), 0)
            upgraded = next(
                session
                for session in config.sessions
                if session.display_name == "Nested Readable Probe Group"
            )
            self.assertEqual(upgraded.display_name_status, "resolved")
            self.assertEqual(upgraded.display_name_source, "contact.remarkName")

    def test_persistent_all_wechat_groups_probe_failure_blocks_before_history(self):
        config = sample_config(enabled=True)
        executor_called = False

        def fake_executor(plan: dict) -> dict:
            nonlocal executor_called
            executor_called = True
            return {"status": "success"}

        result = real_trial_run_plan(
            config,
            all_wechat_groups_payload(),
            executor=fake_executor,
            session_probe=lambda _config: {
                "status": "failed",
                "error_code": "session_probe_unavailable",
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "persistent_real_read_session_probe_failed")
        self.assertEqual(result["scope"]["scope_mode"], "all_wechat_groups")
        self.assertEqual(result["scope"]["source_status"], "failed")
        self.assertTrue(result["execution"]["no_real_read_executed"])
        self.assertFalse(executor_called)
        assert_no_sensitive_fields(self, result)

    def test_persistent_scheduled_trigger_requires_schedule_enabled(self):
        disabled = real_trial_run_plan(
            sample_config(enabled=True, schedule_enabled=False),
            persistent_payload(trigger="scheduled"),
            executor=lambda plan: {"status": "success"},
        )
        enabled = real_trial_run_plan(
            sample_config(enabled=True, schedule_enabled=True),
            persistent_payload(trigger="scheduled"),
            executor=lambda plan: {
                "status": "success",
                "sessions_total": plan["selected_group_count"],
                "sessions_success": plan["selected_group_count"],
            },
        )

        self.assertEqual(disabled["status"], "blocked")
        self.assertEqual(disabled["error_code"], "persistent_real_read_schedule_disabled")
        self.assertTrue(disabled["execution"]["no_real_read_executed"])
        self.assertEqual(enabled["status"], "success")
        self.assertEqual(enabled["trigger"], "scheduled")
        assert_no_sensitive_fields(self, disabled)
        assert_no_sensitive_fields(self, enabled)

    def test_paused_persistent_authorization_blocks_real_read(self):
        config = sample_config(enabled=True, paused=True)

        result = real_trial_run_plan(config, persistent_payload())

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "persistent_real_read_paused")
        self.assertFalse(result["will_run"])
        self.assertTrue(result["execution"]["no_real_read_executed"])
        assert_no_sensitive_fields(self, result)

    def test_persistent_mode_reuses_configurable_window_limits(self):
        config = sample_config(enabled=True, max_lookback_days=7)

        result = real_trial_run_plan(
            config,
            persistent_payload(lookback_days=30),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "expanded_trial_lookback_days_too_large")
        self.assertEqual(result["limits"]["limit_reason"], "exceeds_configured_lookback")
        self.assertFalse(result["will_run"])
        assert_no_sensitive_fields(self, result)

    def test_persistent_mode_blocks_non_whitelisted_or_unknown_group_scope(self):
        config = sample_config(enabled=True)

        result = real_trial_run_plan(
            config,
            persistent_payload(include_all_enabled_whitelist=False, group_ids=["group-a", "group-d"]),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "persistent_real_read_group_scope_invalid")
        self.assertFalse(result["will_run"])
        assert_no_sensitive_fields(self, result)

    def test_persistent_whitelist_scope_still_uses_enabled_whitelist_only(self):
        config = sample_config(enabled=True)

        def fake_executor(plan: dict) -> dict:
            self.assertEqual(plan["scope_mode"], "configurable_window")
            self.assertEqual(plan["selected_group_count"], 2)
            self.assertNotIn("detected_group_count", plan)
            return {
                "status": "success",
                "sessions_total": plan["selected_group_count"],
                "sessions_success": plan["selected_group_count"],
            }

        result = real_trial_run_plan(
            config,
            persistent_payload(include_all_enabled_whitelist=True),
            executor=fake_executor,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["scope"]["scope_mode"], "configurable_window")
        self.assertEqual(result["scope"]["enabled_whitelist_count"], 2)
        self.assertEqual(result["scope"]["selected_group_count"], 2)
        assert_no_sensitive_fields(self, result)

    def test_status_and_config_center_expose_persistent_authorization_contract(self):
        config = sample_config(enabled=True, schedule_enabled=True)

        status_payload = safe_status_payload(config)
        config_payload = safe_config_payload(config)
        center_payload = config_center_payload(config)

        for payload in (status_payload, config_payload):
            contract = payload["real_trial"]["persistent_authorization"] if "real_trial" in payload else payload["wx_cli"]["persistent_authorization"]
            self.assertEqual(contract["authorization_mode"], "persistent")
            self.assertTrue(contract["enabled"])
            self.assertFalse(contract["paused"])
            self.assertTrue(contract["schedule_enabled"])
            self.assertEqual(contract["default_lookback_days"], 30)
            self.assertEqual(contract["interval_minutes"], 45)
            self.assertFalse(contract["real_read_enabled_after"])
            assert_no_sensitive_fields(self, payload)

        self.assertTrue(center_payload["status"]["persistent_authorization"]["enabled"])
        self.assertTrue(center_payload["safety"]["persistent_real_read"]["schedule_enabled"])

    def test_config_center_full_payload_omits_paths_and_member_lists_for_safety_scan(self):
        config = sample_config(enabled=False)

        payload = config_center_payload(config)

        paths = key_paths(payload)
        forbidden_exact = {
            "status.latest_trial.sqlite_path",
            "editable.sessions[].member_name_options",
            "editable.sessions[].roster_member_names",
            "editable.sessions[].member_options.names",
            "editable.sessions[].member_options.items",
            "editable.sessions[].member_options.appeared_members",
            "editable.sessions[].member_options.roster_members",
            "editable.sessions[].member_options.full_members",
        }
        for path in forbidden_exact:
            self.assertNotIn(path, paths)
        for path in paths:
            self.assertFalse(path.endswith(".db_path"), path)
            self.assertFalse(path.endswith(".database_path"), path)
            self.assertFalse(path.endswith(".sqlite_path"), path)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("sqlite_path", text)
        self.assertNotIn("member_name_options", text)

    def test_config_save_persists_persistent_authorization_without_turning_on_legacy_real_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = sample_config(root, enabled=False)
            config.wx_cli.real_read_enabled = True

            result = save_config_center_payload(
                config,
                {
                    "persistent_real_read": {
                        "enabled": True,
                        "paused": False,
                        "test_account_confirmed": True,
                        "schedule_enabled": True,
                        "interval_minutes": 30,
                        "default_lookback_days": 14,
                    }
                },
            )

            self.assertEqual(result["status"], "saved")
            self.assertTrue(config.wx_cli.persistent_real_read_enabled)
            self.assertTrue(config.wx_cli.persistent_real_read_test_account_confirmed)
            self.assertTrue(config.wx_cli.persistent_real_read_schedule_enabled)
            self.assertEqual(config.wx_cli.persistent_real_read_interval_minutes, 30)
            self.assertEqual(config.wx_cli.persistent_real_read_default_lookback_days, 14)
            self.assertFalse(config.wx_cli.real_read_enabled)
            saved = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("persistent_real_read_enabled: true", saved)
            self.assertIn("real_read_enabled: false", saved)
            self.assertNotIn("\n  real_read_enabled: true\n", saved)

    def test_pause_and_resume_controls_do_not_trigger_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config(Path(tmp), enabled=True)

            paused = persistent_real_read_control_payload(config, {"action": "pause"})
            resumed = persistent_real_read_control_payload(config, {"action": "resume"})

            self.assertEqual(paused["status"], "paused")
            self.assertTrue(paused["persistent_authorization"]["paused"])
            self.assertEqual(resumed["status"], "resumed")
            self.assertFalse(resumed["persistent_authorization"]["paused"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            assert_no_sensitive_fields(self, paused)
            assert_no_sensitive_fields(self, resumed)

    def test_repeated_persistent_runs_dedupe_raw_messages_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = sample_config(root, enabled=True)
            conn = setup_database(config)

            def collecting_executor(plan: dict) -> object:
                message = NormalizedMessage(
                    session_external_id="group-a",
                    session_name="测试群A",
                    message_external_id="message-1",
                    local_id="local-1",
                    sender_display_name="发送人甲",
                    sender_raw_id=None,
                    sent_at="2026-05-20T10:00:00+08:00",
                    message_type="text",
                    content_text="请明天跟进并回复报价确认",
                    raw_payload={"source": "fixture"},
                )
                return collect_normalized_messages(
                    config,
                    conn,
                    [message],
                    mode="persistent_real_read",
                )

            first = real_trial_run_plan(
                config,
                persistent_payload(group_ids=["group-a"], include_all_enabled_whitelist=False),
                conn=conn,
                executor=collecting_executor,
            )
            second = real_trial_run_plan(
                config,
                persistent_payload(group_ids=["group-a"], include_all_enabled_whitelist=False),
                conn=conn,
                executor=collecting_executor,
            )

            self.assertEqual(first["status"], "success")
            self.assertEqual(first["execution_summary"]["raw_messages_inserted"], 1)
            self.assertEqual(first["execution_summary"]["candidate_items_created"], 1)
            self.assertEqual(second["status"], "success")
            self.assertEqual(second["execution_summary"]["raw_messages_inserted"], 0)
            self.assertEqual(second["execution_summary"]["raw_messages_duplicated"], 1)
            self.assertEqual(second["execution_summary"]["candidate_items_created"], 0)
            self.assertEqual(conn.execute("select count(*) from raw_messages").fetchone()[0], 1)
            self.assertEqual(conn.execute("select count(*) from candidate_items").fetchone()[0], 1)
            assert_no_sensitive_fields(self, first)
            assert_no_sensitive_fields(self, second)


if __name__ == "__main__":
    unittest.main()
