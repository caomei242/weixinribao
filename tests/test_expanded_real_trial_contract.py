from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, SessionConfig, WxCliConfig
from wechat_feedback_app.routes import (
    config_center_payload,
    real_trial_run_plan,
    safe_config_payload,
    safe_status_payload,
    save_config_center_payload,
)


def sample_config(
    root: Path | None = None, *, max_lookback_days: float = 30
) -> AppConfig:
    return AppConfig(
        root=root or Path("/tmp/wechat-feedback-configurable-window-test"),
        wx_cli=WxCliConfig(
            mode="real",
            real_read_enabled=False,
            expanded_real_lookback_days=max_lookback_days,
            expanded_real_max_groups=3,
            expanded_real_max_total_messages=900,
            expanded_real_max_messages_per_group=300,
            expanded_real_batch_limit=2,
        ),
        sessions=[
            SessionConfig("group-a", "测试群A", enabled=True, is_whitelisted=True),
            SessionConfig("group-b", "测试群B", enabled=True, is_whitelisted=True),
            SessionConfig("group-c", "测试群C", enabled=False, is_whitelisted=True),
        ],
    )


def authorized_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "scope_mode": "configurable_window",
        "confirmed": True,
        "authorize_expanded_real_read_trial": True,
        "test_wechat_account_confirmed": True,
        "one_time_expanded_trial": True,
        "group_ids": ["group-a", "group-b"],
        "max_total_messages": 800,
        "max_messages_per_group": 250,
        "batch_limit": 1,
    }
    payload.update(overrides)
    return payload


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
        "group-a",
        "group-b",
        "member_name_options",
        "raw_payload",
        '"key":',
    ):
        testcase.assertNotIn(forbidden, text)


class ExpandedRealTrialContractTest(unittest.TestCase):
    def assert_window_summary(
        self, result: dict, *, requested: int, effective: int, max_allowed: float
    ) -> None:
        for container in (result["scope"], result["limits"]):
            self.assertEqual(container["requested_lookback_days"], requested)
            self.assertEqual(container["effective_lookback_days"], effective)
            self.assertEqual(container["max_allowed_lookback_days"], max_allowed)
            self.assertIn("window_start", container)
            self.assertIn("window_end", container)
            self.assertIn("limit_reason", container)

    def test_configurable_window_defaults_to_thirty_day_preset_without_enabling_read(self):
        result = real_trial_run_plan(sample_config(), authorized_payload())

        self.assertEqual(result["status"], "dry_run_ready")
        self.assertFalse(result["will_run"])
        self.assertFalse(result["real_read_enabled"])
        self.assertEqual(result["scope"]["scope_mode"], "configurable_window")
        self.assertEqual(result["scope"]["preset"], "last_30_days")
        self.assertTrue(result["scope"]["default_window_used"])
        self.assertEqual(result["limits"]["limit_reason"], "within_configured_limit")
        self.assert_window_summary(result, requested=30, effective=30, max_allowed=30)
        self.assertEqual(result["error_code"], "real_trial_execution_entry_not_opened")
        self.assertFalse(result["execution"]["entry_opened"])
        self.assertFalse(result["execution"]["will_execute_wx_history"])
        self.assertTrue(result["execution"]["no_real_read_executed"])
        self.assertFalse(result["execution"]["real_read_enabled_after"])
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_supports_seven_and_thirty_day_lookback(self):
        seven = real_trial_run_plan(
            sample_config(), authorized_payload(lookback_days=7)
        )
        thirty = real_trial_run_plan(
            sample_config(), authorized_payload(lookback_days=30)
        )

        self.assertEqual(seven["status"], "dry_run_ready")
        self.assertEqual(seven["scope"]["preset"], "custom_window")
        self.assert_window_summary(seven, requested=7, effective=7, max_allowed=30)
        self.assertEqual(thirty["status"], "dry_run_ready")
        self.assertEqual(thirty["scope"]["preset"], "last_30_days")
        self.assert_window_summary(thirty, requested=30, effective=30, max_allowed=30)
        assert_no_sensitive_fields(self, seven)
        assert_no_sensitive_fields(self, thirty)

    def test_configurable_window_supports_sixty_days_when_config_allows_it(self):
        config = sample_config(max_lookback_days=60)

        result = real_trial_run_plan(config, authorized_payload(lookback_days=60))

        self.assertEqual(result["status"], "dry_run_ready")
        self.assertFalse(result["will_run"])
        self.assert_window_summary(result, requested=60, effective=60, max_allowed=60)
        self.assertEqual(result["limits"]["limit_reason"], "within_configured_limit")
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_supports_explicit_start_and_end_time(self):
        result = real_trial_run_plan(
            sample_config(),
            authorized_payload(
                start_time="2026-05-01T00:00:00+00:00",
                end_time="2026-05-08T00:00:00+00:00",
            ),
        )

        self.assertEqual(result["status"], "dry_run_ready")
        self.assertEqual(result["scope"]["time_range_mode"], "explicit_range")
        self.assertFalse(result["scope"]["default_window_used"])
        self.assert_window_summary(result, requested=7, effective=7, max_allowed=30)
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_blocks_over_configured_limit_with_reason(self):
        result = real_trial_run_plan(
            sample_config(), authorized_payload(lookback_days=31)
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "expanded_trial_lookback_days_too_large")
        self.assertEqual(result["reason_code"], "expanded_trial_lookback_days_too_large")
        self.assertEqual(result["limits"]["limit_reason"], "exceeds_configured_lookback")
        self.assert_window_summary(result, requested=31, effective=31, max_allowed=30)
        self.assertFalse(result["will_run"])
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_blocks_when_windows_config_still_two_hours(self):
        config = sample_config(max_lookback_days=0.0833)

        result = real_trial_run_plan(config, authorized_payload(lookback_days=30))

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "expanded_trial_lookback_days_too_large")
        self.assertEqual(result["limits"]["limit_reason"], "exceeds_configured_lookback")
        self.assert_window_summary(result, requested=30, effective=30, max_allowed=0.0833)
        self.assertFalse(result["will_run"])
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_blocks_illegal_window_parameters(self):
        bad_days = real_trial_run_plan(
            sample_config(), authorized_payload(lookback_days="abc")
        )
        bad_range = real_trial_run_plan(
            sample_config(),
            authorized_payload(
                start_time="2026-05-08T00:00:00+00:00",
                end_time="2026-05-01T00:00:00+00:00",
            ),
        )

        self.assertEqual(bad_days["status"], "blocked")
        self.assertEqual(bad_days["error_code"], "expanded_trial_lookback_days_invalid")
        self.assertEqual(bad_range["status"], "blocked")
        self.assertEqual(bad_range["error_code"], "expanded_trial_time_range_invalid")
        assert_no_sensitive_fields(self, bad_days)
        assert_no_sensitive_fields(self, bad_range)

    def test_configurable_window_blocks_without_explicit_authorization(self):
        result = real_trial_run_plan(
            sample_config(),
            {
                "trial_mode": "last_30_days",
                "confirmed": True,
                "test_wechat_account_confirmed": True,
                "one_time_expanded_trial": True,
                "group_ids": ["wxid_secret_group"],
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "expanded_trial_authorization_required")
        self.assertFalse(result["will_run"])
        self.assertEqual(result["failure_summary"]["error_count"], 1)
        assert_no_sensitive_fields(self, result)

    def test_execute_once_requires_authorization_token_or_marker(self):
        result = real_trial_run_plan(
            sample_config(),
            authorized_payload(execute_once=True, lookback_days=30),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "one_time_authorization_token_required")
        self.assertFalse(result["will_run"])
        self.assertFalse(result["real_read_enabled"])
        assert_no_sensitive_fields(self, result)

    def test_execute_once_enters_fake_execution_path_when_authorized(self):
        config = sample_config(max_lookback_days=30)
        config.wx_cli.real_read_enabled = False

        def fake_executor(plan: dict) -> dict:
            self.assertEqual(plan["window"]["effective_lookback_days"], 30)
            self.assertEqual(plan["window"]["max_allowed_lookback_days"], 30)
            self.assertEqual(plan["selected_group_count"], 2)
            self.assertFalse(plan["real_read_enabled_before"])
            return {
                "status": "success",
                "error_code": "",
                "sessions_total": 2,
                "sessions_success": 2,
                "sessions_failed": 0,
                "raw_messages_seen": 12,
                "raw_messages_inserted": 10,
                "raw_messages_duplicated": 2,
                "candidate_items_created": 3,
                "candidate_items_updated": 1,
            }

        result = real_trial_run_plan(
            config,
            authorized_payload(
                execute_once=True,
                one_time_authorization_token="test-token",
                lookback_days=30,
            ),
            executor=fake_executor,
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["will_run"])
        self.assertFalse(result["real_read_enabled"])
        self.assertFalse(result["real_read_enabled_after"])
        self.assertTrue(result["execution"]["entry_opened"])
        self.assertFalse(result["execution"]["no_real_read_executed"])
        self.assertFalse(config.wx_cli.real_read_enabled)
        self.assertEqual(result["execution_summary"]["raw_messages_inserted"], 10)
        self.assertEqual(result["execution_summary"]["candidate_items_created"], 3)
        assert_no_sensitive_fields(self, result)

    def test_execute_once_returns_failed_summary_without_persisting_real_read_enabled(self):
        config = sample_config(max_lookback_days=30)
        config.wx_cli.real_read_enabled = False

        result = real_trial_run_plan(
            config,
            authorized_payload(
                execute_once=True,
                one_time_authorization_marker=True,
                lookback_days=30,
            ),
            executor=lambda plan: {
                "status": "failed",
                "error_code": "wx_cli_failed",
                "sessions_total": plan["selected_group_count"],
                "sessions_success": 0,
                "sessions_failed": plan["selected_group_count"],
                "raw_messages_seen": 0,
                "raw_messages_inserted": 0,
                "raw_messages_duplicated": 0,
                "candidate_items_created": 0,
                "candidate_items_updated": 0,
            },
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "wx_cli_failed")
        self.assertTrue(result["will_run"])
        self.assertEqual(result["failure_summary"]["failed_group_count"], 2)
        self.assertFalse(result["real_read_enabled_after"])
        self.assertFalse(config.wx_cli.real_read_enabled)
        assert_no_sensitive_fields(self, result)

    def test_configurable_window_compat_alias_preserves_old_expanded_30d_entry(self):
        result = real_trial_run_plan(
            sample_config(),
            authorized_payload(scope_mode="expanded_30d", lookback_days=30),
        )

        self.assertEqual(result["status"], "dry_run_ready")
        self.assertEqual(result["scope"]["scope_mode"], "configurable_window")
        self.assert_window_summary(result, requested=30, effective=30, max_allowed=30)
        assert_no_sensitive_fields(self, result)

    def test_config_and_status_expose_configurable_contract_without_enabling_real_read(self):
        config = sample_config(max_lookback_days=60)

        for payload in (safe_status_payload(config), safe_config_payload(config)):
            text = json.dumps(payload, ensure_ascii=False)
            self.assertIn("expanded_trial", text)
            self.assertIn('"scope_mode": "configurable_window"', text)
            self.assertIn('"default_preset_lookback_days": 30', text)
            self.assertIn('"max_allowed_lookback_days": 60', text)
            self.assertIn('"supports_start_end_time": true', text)
            self.assertIn('"multi_group_supported": true', text)
            self.assertNotIn('"real_read_enabled": true', text)
            assert_no_sensitive_fields(self, payload)
        config_center = config_center_payload(config)
        text = json.dumps(config_center, ensure_ascii=False)
        self.assertIn('"scope_mode": "configurable_window"', text)
        self.assertIn('"max_allowed_lookback_days": 60', text)
        self.assertNotIn('"real_read_enabled": true', text)

    def test_config_save_keeps_default_off_and_allows_future_window_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = sample_config(root)
            config.wx_cli.real_read_enabled = True

            saved = save_config_center_payload(
                config,
                {
                    "trial_defaults": {
                        "limit": 999,
                        "lookback_hours": 99,
                        "expanded_trial": {
                            "max_allowed_lookback_days": 90,
                            "max_groups": 99,
                            "max_total_messages": 99999,
                            "max_messages_per_group": 9999,
                            "batch_limit": 99,
                        },
                    }
                },
            )

            self.assertEqual(saved["status"], "saved")
            self.assertFalse(config.wx_cli.real_read_enabled)
            self.assertEqual(config.wx_cli.real_lookback_hours, 2)
            self.assertEqual(config.wx_cli.real_limit, 50)
            self.assertEqual(config.wx_cli.expanded_real_lookback_days, 90)
            self.assertEqual(config.wx_cli.expanded_real_max_groups, 50)
            self.assertEqual(config.wx_cli.expanded_real_max_total_messages, 10000)
            self.assertEqual(config.wx_cli.expanded_real_max_messages_per_group, 1000)
            self.assertEqual(config.wx_cli.expanded_real_batch_limit, 12)
            saved_text = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("real_read_enabled: false", saved_text)
            self.assertNotIn("real_read_enabled: true", saved_text)
            self.assertIn("expanded_real_lookback_days: 90", saved_text)

    def test_legacy_recent50_plan_still_uses_single_group_guard(self):
        result = real_trial_run_plan(
            sample_config(),
            {
                "confirmed": True,
                "preset": "recent50",
                "limit": 50,
            },
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "real_trial_whitelist_count_invalid")
        self.assertFalse(result["will_run"])


if __name__ == "__main__":
    unittest.main()
