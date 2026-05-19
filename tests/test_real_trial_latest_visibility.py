import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, PersonConfig, SessionConfig, WxCliConfig
from wechat_feedback_app.db import init_db
from wechat_feedback_app.routes import (
    config_center_payload,
    daily_control_payload,
    export_template_preview_payload,
    draft_report_preview_payload,
    inbox_v1_payload,
    import_latest_real_trial_candidates,
    latest_real_trial_payload,
    real_trial_candidate_messages_payload,
    real_trial_latest_items_payload,
    real_trial_latest_messages_payload,
    real_trial_run_plan,
    save_sender_mapping_payload,
    save_config_center_payload,
)


class RealTrialLatestVisibilityTest(unittest.TestCase):
    def test_latest_real_trial_payload_returns_counts_and_relative_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            export_dir = root / "exports" / "real_trial_recent50_20260518-105050"
            db_path.parent.mkdir(parents=True)
            export_dir.mkdir(parents=True)
            self._write_trial_db(db_path)

            config = AppConfig(root=root, wx_cli=WxCliConfig(mode="fixture"))

            payload = latest_real_trial_payload(config)

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["mode"], "real")
            self.assertEqual(payload["source_label"], "recent50")
            self.assertFalse(payload["current_service_is_real"])
            self.assertFalse(payload["default_real_read_enabled"])
            self.assertEqual(payload["raw_count"], 2)
            self.assertEqual(payload["candidate_count"], 2)
            self.assertEqual(payload["risk_count"], 1)
            self.assertEqual(payload["candidate_status_counts"]["pending"], 1)
            self.assertEqual(payload["candidate_status_counts"]["confirmed"], 1)
            self.assertEqual(
                payload["sqlite_path"],
                "data/real_trial_recent50_20260518-105050.sqlite3",
            )
            self.assertEqual(
                payload["export_directory"],
                "exports/real_trial_recent50_20260518-105050",
            )
            self.assertTrue(payload["sqlite_exists"])
            self.assertTrue(payload["export_directory_exists"])
            self.assertTrue(payload["fixture_service_notice"])

            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_TITLE", text)
            self.assertNotIn("SECRET_SUMMARY", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)

    def test_latest_real_trial_payload_handles_missing_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig(root=Path(tmp))

            payload = latest_real_trial_payload(config)

            self.assertEqual(payload["status"], "not_found")
            self.assertEqual(payload["raw_count"], 0)
            self.assertEqual(payload["candidate_count"], 0)
            self.assertEqual(payload["risk_count"], 0)

    def test_static_page_has_real_trial_summary_without_real_content_fields(self):
        app_js = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "wechat_feedback_app"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/real-trial/latest", app_js)
        self.assertIn("renderRealTrialSummary", app_js)
        self.assertIn("raw_count", app_js)
        self.assertIn("candidate_count", app_js)
        self.assertIn("risk_count", app_js)
        self.assertNotIn("realTrial.content_text", app_js)
        self.assertNotIn("realTrial.raw_payload_json", app_js)
        self.assertNotIn("realTrial.session_name", app_js)

    def test_index_cache_busts_static_assets(self):
        index_html = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "wechat_feedback_app"
            / "static"
            / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("/static/styles.css?v=20260518-inbox-v1", index_html)
        self.assertIn("/static/app.js?v=20260518-inbox-v1", index_html)

    def test_real_trial_summary_has_redacted_error_fallback(self):
        app_js = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "wechat_feedback_app"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("catch", app_js)
        self.assertIn("真实试读摘要暂不可用", app_js)
        self.assertIn("api_error", app_js)
        self.assertNotIn("error.message", app_js)
        self.assertNotIn("error.stack", app_js)

    def test_config_center_save_never_persists_real_read_enabled_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root=root,
                wx_cli=WxCliConfig(mode="real", real_read_enabled=False),
                sessions=[],
                internal_people=[],
            )

            saved = save_config_center_payload(
                config,
                {
                    "sessions": [
                        {
                            "external_id": "session-1",
                            "display_name": "可见会话",
                            "customer_name": "客户",
                            "channel_name": "",
                    "module_name": "模块",
                    "owner_name": "负责人",
                    "customer_stage": "试点验证",
                    "group_type": "客户项目群",
                    "common_contacts": ["对接人A", "对接人B"],
                    "reply_notes": "先内部确认再回复",
                    "is_whitelisted": True,
                    "enabled": True,
                }
                    ],
                    "internal_people": [
                        {"person_name": "我方A", "aliases": ["A", "A同事"]}
                    ],
                    "risk": {
                        "keywords": ["投诉", "退款"],
                        "sensitive_keywords": ["身份证"],
                    },
                    "trial_defaults": {
                        "limit": 999,
                        "lookback_hours": 99,
                        "start_at": "2026-05-18T09:00",
                        "end_at": "2026-05-18T11:00",
                        "real_read_enabled": True,
                    },
                },
            )

            self.assertEqual(saved["status"], "saved")
            self.assertFalse(saved["real_read_enabled"])
            self.assertFalse(config.wx_cli.real_read_enabled)
            self.assertEqual(config.wx_cli.real_limit, 50)
            self.assertEqual(config.wx_cli.real_lookback_hours, 2)
            self.assertEqual(config.wx_cli.real_start_at, "2026-05-18T09:00")
            self.assertEqual(config.wx_cli.real_end_at, "2026-05-18T11:00")
            self.assertEqual(len(config.sessions), 1)
            self.assertEqual(config.sessions[0].customer_stage, "试点验证")
            self.assertEqual(config.sessions[0].group_type, "客户项目群")
            self.assertEqual(config.sessions[0].common_contacts, ["对接人A", "对接人B"])
            self.assertEqual(config.sessions[0].reply_notes, "先内部确认再回复")
            self.assertEqual(config.internal_people[0].aliases, ["A", "A同事"])
            saved_text = (root / "config" / "app.yaml").read_text(encoding="utf-8")
            self.assertIn("real_read_enabled: false", saved_text)
            self.assertNotIn("real_read_enabled: true", saved_text)
            self.assertIn("real_start_at: 2026-05-18T09:00", saved_text)
            self.assertIn("real_end_at: 2026-05-18T11:00", saved_text)
            self.assertIn("customer_stage: 试点验证", saved_text)
            self.assertIn("group_type: 客户项目群", saved_text)

    def test_config_center_payload_is_editable_but_keeps_safety_summary(self):
        config = AppConfig(
            wx_cli=WxCliConfig(mode="fixture", real_read_enabled=False),
            sessions=[SessionConfig("session-1", "会话一", enabled=True)],
            internal_people=[PersonConfig("我方A", ["A"])],
        )

        payload = config_center_payload(config)

        self.assertEqual(payload["status"]["mode"], "fixture")
        self.assertFalse(payload["status"]["real_read_enabled"])
        self.assertEqual(payload["status"]["enabled_whitelist_count"], 1)
        self.assertEqual(payload["editable"]["sessions"][0]["display_name"], "会话一")
        self.assertIn("customer_stage", payload["editable"]["sessions"][0])
        self.assertIn("group_type", payload["editable"]["sessions"][0])
        self.assertIn("common_contacts", payload["editable"]["sessions"][0])
        self.assertIn("reply_notes", payload["editable"]["sessions"][0])
        self.assertEqual(payload["editable"]["internal_people"][0]["person_name"], "我方A")
        self.assertEqual(payload["editable"]["trial_defaults"]["limit"], 50)
        self.assertIn("start_at", payload["editable"]["trial_defaults"])
        self.assertIn("end_at", payload["editable"]["trial_defaults"])
        self.assertFalse(payload["safety"]["default_real_read_enabled"])

    def test_inbox_v1_payload_connects_trial_messages_candidates_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                root=root,
                wx_cli=WxCliConfig(mode="fixture", real_read_enabled=False),
                sessions=[
                    SessionConfig(
                        "trial",
                        "试点会话",
                        customer_name="客户A",
                        module_name="售后",
                        owner_name="负责人A",
                        customer_stage="试点验证",
                        group_type="客户项目群",
                        common_contacts=["联系人A"],
                        reply_notes="内部确认后回复",
                    )
                ],
            )
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = inbox_v1_payload(config, main_conn, "2026-05-18")

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["title"], "微信反馈防漏收件箱 V1")
            self.assertFalse(payload["safety"]["default_real_read_enabled"])
            self.assertEqual(payload["top_status"]["raw_count"], 2)
            self.assertEqual(payload["top_status"]["candidate_count"], 2)
            self.assertEqual(payload["top_status"]["risk_count"], 1)
            self.assertEqual(payload["top_status"]["pending_count"], 0)
            self.assertIn("50 条是原始消息", payload["message_vs_candidate_explain"])
            self.assertIn("3 条是抽出来的候选事项", payload["message_vs_candidate_explain"])
            self.assertEqual(
                [step["key"] for step in payload["workflow_steps"]],
                [
                    "trial_read",
                    "message_review",
                    "sender_identity",
                    "candidate_items",
                    "group_customer_tags",
                    "manual_confirm",
                    "draft_report",
                    "transfer_summary",
                ],
            )
            self.assertEqual(payload["group_profile"]["customer_name"], "客户A")
            self.assertEqual(payload["group_profile"]["group_owner"], "负责人A")
            self.assertEqual(payload["group_profile"]["customer_stage"], "试点验证")
            self.assertEqual(payload["group_profile"]["group_type"], "客户项目群")
            self.assertEqual(payload["group_profile"]["common_contacts_count"], 1)
            self.assertTrue(payload["group_profile"]["reply_notes_configured"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_TITLE", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("raw_payload_json", text)

    def test_inbox_v1_payload_adds_p0_human_status_and_trial_draft_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root, wx_cli=WxCliConfig(mode="fixture", real_read_enabled=False))
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = inbox_v1_payload(config, main_conn, "2026-05-18")

            self.assertEqual(
                [card["label"] for card in payload["human_status"]["cards"]],
                ["服务健康", "真实读取", "最近一次可用结果", "候选事项", "草稿日报", "今日收口"],
            )
            self.assertTrue(payload["human_status"]["diagnostic_details"]["collapsed"])
            self.assertFalse(payload["safety"]["default_real_read_enabled"])
            self.assertTrue(payload["trial_draft_prompt"]["visible"])
            self.assertIn("最近试读", payload["trial_draft_prompt"]["message"])
            self.assertIn("生成试读草稿", payload["trial_draft_prompt"]["primary_action_label"])
            self.assertEqual(payload["suggested_draft_data_source"], "real_trial")
            human_text = json.dumps(payload["human_status"], ensure_ascii=False)
            self.assertNotIn("workspace", human_text)
            self.assertNotIn("real_trial", human_text)
            self.assertNotIn("binary", human_text)
            self.assertNotIn("formal_write", human_text)
            self.assertNotIn("local_review", human_text)
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def test_inbox_v1_payload_exposes_unified_candidate_inbox_when_workspace_empty_and_trial_has_three_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root, wx_cli=WxCliConfig(mode="fixture", real_read_enabled=False))
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db, candidate_count=3)

            payload = inbox_v1_payload(config, main_conn, "2026-05-18")

            inbox = payload["candidate_inbox"]
            self.assertEqual(inbox["count"], 3)
            self.assertFalse(inbox["requires_source_switch"])
            self.assertEqual(inbox["primary_action"]["action"], "import_to_workspace")
            self.assertEqual(inbox["items"][0]["source_label"], "来自最近试读")
            self.assertIn("summary_safe", inbox["items"][0])
            self.assertIn("reason_safe", inbox["items"][0])
            self.assertIn("还有 3 条候选待确认", inbox["summary_label"])
            self.assertIn("无需先切换数据来源", inbox["source_hint"])
            human_text = json.dumps(
                {
                    "summary_label": inbox["summary_label"],
                    "source_hint": inbox["source_hint"],
                    "primary_label": inbox["primary_action"]["label"],
                    "items": [
                        {
                            "display_id": item["display_id"],
                            "human_type": item["human_type"],
                            "human_status": item["human_status"],
                            "source_label": item["source_label"],
                            "action_label": item["action_label"],
                            "summary_safe": item["summary_safe"],
                            "reason_safe": item["reason_safe"],
                            "risk_label": item["risk_label"],
                            "owner_label": item["owner_label"],
                            "next_step_label": item["next_step_label"],
                        }
                        for item in inbox["items"]
                    ],
                },
                ensure_ascii=False,
            )
            for token in [
                "workspace",
                "real_trial",
                "pending",
                "none",
                "tech",
                "ops",
                "resolved",
                "real_read_disabled",
                "formal_write",
            ]:
                self.assertNotIn(token, human_text)

    def test_latest_real_trial_items_return_candidate_summary_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            export_dir = root / "exports" / "real_trial_recent50_20260518-105050"
            db_path.parent.mkdir(parents=True)
            export_dir.mkdir(parents=True)
            self._write_trial_db(db_path)
            config = AppConfig(root=root)

            payload = real_trial_latest_items_payload(config)

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["items"][0]["item_code"], "R-001")
            self.assertIn("title", payload["items"][0])
            self.assertIn("summary", payload["items"][0])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_SENDER", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("evidence", text)

    def test_real_trial_candidate_visible_text_redacts_wxid_in_items_draft_and_transfer_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            db_path.parent.mkdir(parents=True)
            self._write_trial_db(db_path)
            self._inject_visible_wxid_candidate_text(db_path)
            config = AppConfig(root=root)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)

            items_payload = real_trial_latest_items_payload(config)
            draft_payload = draft_report_preview_payload(
                config,
                main_conn,
                {"control_date": "2026-05-18", "data_source": "real_trial"},
            )
            transfer_payload = export_template_preview_payload(
                config,
                main_conn,
                {
                    "export_date": "2026-05-18",
                    "template_id": "product_tech_summary",
                    "data_source": "real_trial",
                },
            )

            text = json.dumps(
                {
                    "items": items_payload,
                    "draft": draft_payload,
                    "transfer": transfer_payload,
                },
                ensure_ascii=False,
            )
            self.assertFalse("wxid" in text.lower(), "response contains wxid marker")
            self.assertIn("[敏感信息已脱敏]", text)

    def test_latest_real_trial_items_include_p0_display_reason_and_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            db_path.parent.mkdir(parents=True)
            self._write_trial_db(db_path)
            config = AppConfig(root=root)

            payload = real_trial_latest_items_payload(config)

            first = payload["items"][0]
            self.assertEqual(first["human_item_type"], "客户需求")
            self.assertIn("抽取理由", first["extraction_reason"])
            self.assertEqual(first["source_message_count"], 2)
            self.assertEqual(
                first["detail_actions"],
                ["确认", "驳回", "改类型", "补充说明", "撤销"],
            )
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def test_real_trial_run_plan_rejects_missing_or_multiple_whitelist(self):
        empty_config = AppConfig(sessions=[])
        multi_config = AppConfig(
            sessions=[
                SessionConfig("one", "one", enabled=True, is_whitelisted=True),
                SessionConfig("two", "two", enabled=True, is_whitelisted=True),
            ]
        )

        empty_result = real_trial_run_plan(empty_config, {"confirmed": True, "limit": 50})
        multi_result = real_trial_run_plan(multi_config, {"confirmed": True, "limit": 50})

        self.assertEqual(empty_result["status"], "blocked")
        self.assertEqual(empty_result["error_code"], "real_trial_whitelist_count_invalid")
        self.assertEqual(multi_result["status"], "blocked")
        self.assertEqual(multi_result["error_code"], "real_trial_whitelist_count_invalid")
        self.assertFalse(empty_result["will_run"])
        self.assertFalse(multi_result["will_run"])

    def test_real_trial_run_plan_rejects_invalid_limit(self):
        config = AppConfig(
            sessions=[SessionConfig("one", "one", enabled=True, is_whitelisted=True)]
        )

        result = real_trial_run_plan(config, {"confirmed": True, "limit": "abc"})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error_code"], "real_trial_limit_invalid")
        self.assertFalse(result["will_run"])

    def test_real_trial_run_plan_rejects_missing_time_range_unless_recent50(self):
        config = AppConfig(
            sessions=[SessionConfig("one", "one", enabled=True, is_whitelisted=True)]
        )

        blocked = real_trial_run_plan(
            config,
            {
                "confirmed": True,
                "limit": 50,
                "lookback_hours": "",
                "start_at": "",
                "end_at": "",
                "preset": "",
            },
        )
        ready = real_trial_run_plan(
            config,
            {
                "confirmed": True,
                "limit": 50,
                "lookback_hours": "",
                "start_at": "",
                "end_at": "",
                "preset": "recent50",
            },
        )

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["error_code"], "real_trial_time_range_required")
        self.assertFalse(blocked["will_run"])
        self.assertEqual(ready["status"], "dry_run_ready")
        self.assertEqual(ready["scope"]["preset"], "recent50")

    def test_import_latest_real_trial_candidates_is_idempotent_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            first = import_latest_real_trial_candidates(config, main_conn)
            second = import_latest_real_trial_candidates(config, main_conn)

            count = main_conn.execute("select count(*) from candidate_items").fetchone()[0]
            raw_count = main_conn.execute("select count(*) from raw_messages").fetchone()[0]
            self.assertEqual(first["status"], "imported")
            self.assertEqual(first["imported_count"], 2)
            self.assertEqual(first["duplicated_count"], 0)
            self.assertEqual(second["status"], "imported")
            self.assertEqual(second["imported_count"], 0)
            self.assertEqual(second["duplicated_count"], 2)
            self.assertEqual(count, 2)
            self.assertEqual(raw_count, 0)
            text = json.dumps(first, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_TITLE", text)
            self.assertNotIn("SECRET_SUMMARY", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertFalse(first["formal_write_enabled"])

    def test_daily_control_exposes_real_trial_actions_when_main_pool_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = daily_control_payload(config, main_conn, "2026-05-18")

            self.assertTrue(payload["real_trial_notice"]["visible"])
            self.assertEqual(
                {action["action"] for action in payload["real_trial_actions"]},
                {"import_to_workspace", "export_templates_from_trial"},
            )
            self.assertIn("本地候选", payload["real_trial_actions"][0]["message"])
            self.assertIn("本地 Markdown", payload["real_trial_actions"][1]["message"])

    def test_export_template_preview_can_use_latest_real_trial_source_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = export_template_preview_payload(
                config,
                main_conn,
                {
                    "export_date": "2026-05-18",
                    "template_id": "daily_review",
                    "data_source": "real_trial",
                },
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data_source"], "real_trial")
            self.assertEqual(payload["item_count"], 2)
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_SENDER", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("evidence", text)

    def test_export_template_preview_defaults_to_unified_pool_and_returns_human_task_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            (root / "data").mkdir(parents=True, exist_ok=True)
            main_conn = sqlite3.connect(root / "data" / "main.sqlite3")
            main_conn.row_factory = sqlite3.Row
            init_db(main_conn)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db, candidate_count=3)

            payload = export_template_preview_payload(
                config,
                main_conn,
                {
                    "export_date": "2026-05-18",
                    "template_id": "product_tech_summary",
                },
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data_source"], "real_trial")
            self.assertEqual(payload["item_count"], 3)
            self.assertEqual(payload["data_source_label"], "最近试读候选")
            self.assertEqual(payload["human_task"]["task_title"], "给内部产品 / 技术同步")
            self.assertTrue(payload["human_task"]["copy_ready"])
            self.assertEqual(payload["human_task"]["candidate_count"], 3)
            human_text = json.dumps(payload["human_task"], ensure_ascii=False)
            for token in [
                "workspace",
                "real_trial",
                "pending",
                "none",
                "tech",
                "ops",
                "resolved",
                "real_read_disabled",
                "formal_write",
            ]:
                self.assertNotIn(token, human_text)

    def test_latest_real_trial_messages_return_local_content_without_forbidden_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = real_trial_latest_messages_payload(config)

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["count"], 2)
            first = payload["messages"][0]
            self.assertEqual(
                {
                    "message_ref",
                    "sent_at",
                    "sender_display_name",
                    "sender_identity",
                    "sender_resolution",
                    "message_type",
                    "content",
                    "linked_candidate_codes",
                    "has_risk",
                    "risk_tags",
                },
                set(first.keys()),
            )
            self.assertEqual(first["content"], "SECRET_BODY_0")
            self.assertEqual(first["sender_display_name"], "未解析微信名")
            self.assertEqual(first["sender_identity"], "unknown")
            self.assertEqual(first["sender_resolution"], "unresolved")
            self.assertEqual(first["linked_candidate_codes"], ["R-001"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("message_external_id", text)
            self.assertNotIn("local_id", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def test_sender_mapping_can_mark_unresolved_sender_without_echoing_raw_identifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(root / "data" / "main.sqlite3")
            conn.row_factory = sqlite3.Row
            init_db(conn)

            result = save_sender_mapping_payload(
                conn,
                {
                    "sender_display_name": "wxid_secret_sender",
                    "role": "internal",
                    "person_name": "本地人工映射",
                    "add_alias": True,
                },
            )

            self.assertEqual(result["status"], "saved")
            self.assertEqual(result["role"], "internal")
            self.assertTrue(result["alias_saved"])
            row = conn.execute(
                """
                select role, person_name
                from people_aliases
                where alias = ?
                """,
                ("wxid_secret_sender",),
            ).fetchone()
            self.assertEqual(dict(row), {"role": "internal", "person_name": "本地人工映射"})
            text = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("wxid_secret_sender", text)

    def test_real_trial_candidate_source_chain_returns_message_context_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(root=root)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_trial_db(trial_db)

            payload = real_trial_candidate_messages_payload(config, 1)

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["candidate_ref"], "R-001")
            self.assertEqual(payload["count"], 2)
            self.assertEqual([row["message_ref"] for row in payload["messages"]], ["m-0001", "m-0002"])
            self.assertEqual(payload["messages"][0]["content"], "SECRET_BODY_0")
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("message_external_id", text)
            self.assertNotIn("local_id", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def test_static_page_exposes_config_center_and_candidate_source_switch(self):
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "src" / "wechat_feedback_app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        index_html = (
            root / "src" / "wechat_feedback_app" / "static" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/config-center", app_js)
        self.assertIn("/api/real-trial/latest/items", app_js)
        self.assertIn("/api/real-trial/run", app_js)
        self.assertIn("openConfigCenter", app_js)
        self.assertIn("renderConfigCenter", app_js)
        self.assertIn("setItemSource", app_js)
        self.assertIn("confirm(", app_js)
        self.assertIn("escapeHtml", app_js)
        self.assertNotIn("renderConfigSummary", app_js)
        self.assertIn("configCenterDialog", index_html)
        self.assertIn("configCenterNav", index_html)
        self.assertIn("trialStartInput", index_html)
        self.assertIn("trialEndInput", index_html)
        self.assertIn("applyTrialPreset", app_js)
        self.assertIn("importRealTrialBtn", index_html)
        self.assertIn("openExportTemplateDialog(\"realTrial\")", app_js)
        self.assertIn("exportDataSource", index_html)
        self.assertIn("推荐使用转述摘要", index_html)
        self.assertIn("realTrialMessagesPanel", index_html)
        self.assertIn("senderReviewPanel", index_html)
        self.assertIn("inboxV1Workspace", index_html)
        self.assertIn("inboxV1Nav", index_html)
        self.assertIn("inboxV1TopStatus", index_html)
        self.assertIn("inboxMainGrid", index_html)
        self.assertIn("candidateInboxPanel", index_html)
        self.assertIn("inboxInspectorPanel", index_html)
        self.assertIn("runtimeGroupProfile", index_html)
        self.assertIn("今日防漏", index_html)
        self.assertIn("试读消息", index_html)
        self.assertIn("候选收件箱", index_html)
        self.assertIn("群 / 客户打标", index_html)
        self.assertIn("草稿日报", index_html)
        self.assertIn("转述摘要", index_html)
        self.assertIn("配置中心", index_html)
        self.assertIn("<summary>更多</summary>", index_html)
        self.assertIn("more-menu", index_html)
        self.assertIn('<button id="exportTemplateBtn">转述摘要</button>', index_html)
        self.assertNotIn('<button id="exportTemplateBtn">导出模板</button>', index_html)
        self.assertNotIn('<button id="configBtn">配置</button>', index_html)
        self.assertLess(index_html.index("更多"), index_html.index("旧版日报"))
        self.assertLess(index_html.index("更多"), index_html.index("旧版待办"))
        self.assertLess(index_html.index("更多"), index_html.index("dailyControlBtn"))
        self.assertIn("客户名称", index_html)
        self.assertIn("群负责人", index_html)
        self.assertIn("业务模块", index_html)
        self.assertIn("客户阶段", index_html)
        self.assertIn("群类型", index_html)
        self.assertIn("常用联系人", index_html)
        self.assertIn("回复注意事项", index_html)
        self.assertIn("微信反馈防漏收件箱 V1", index_html)
        self.assertIn("50 条是原始消息", index_html)
        self.assertIn("3 条是抽出来的候选事项", index_html)
        self.assertIn("/api/inbox/v1", app_js)
        self.assertIn("refreshInboxV1", app_js)
        self.assertIn("customer_stage", app_js)
        self.assertIn("group_type", app_js)
        self.assertIn("common_contacts", app_js)
        self.assertIn("reply_notes", app_js)
        self.assertIn("/api/real-trial/latest/messages", app_js)
        self.assertIn("/api/real-trial/latest/items/${item.id}/messages", app_js)
        self.assertIn("/api/real-trial/sender-map", app_js)
        self.assertIn("renderRealTrialMessages", app_js)
        self.assertIn("saveSenderMapping", app_js)

    def test_static_page_uses_fixed_p0_pages_and_restores_state(self):
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "src" / "wechat_feedback_app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )
        index_html = (
            root / "src" / "wechat_feedback_app" / "static" / "index.html"
        ).read_text(encoding="utf-8")

        for page in ["today", "messages", "candidates", "group-tags", "draft", "transfer", "config"]:
            self.assertIn(f'data-page-target="{page}"', index_html)
            self.assertIn(f'data-page="{page}"', index_html)
        self.assertIn("humanStatusCards", index_html)
        self.assertIn("diagnosticDetails", index_html)
        self.assertIn("trialDraftPrompt", index_html)
        self.assertIn("candidateActionBar", index_html)
        self.assertIn("draftDataSourceChoice", index_html)
        self.assertIn("transferSummaryPage", index_html)
        self.assertIn("configCenterPage", index_html)
        self.assertIn("setWorkspacePage", app_js)
        self.assertIn("restoreWorkspaceState", app_js)
        self.assertIn("saveWorkspaceState", app_js)
        self.assertIn("localStorage", app_js)
        self.assertNotIn("data-scroll-target", index_html)
        self.assertNotIn("data-open-dialog", index_html)
        self.assertNotIn(".showModal()", app_js)

    def _write_trial_db(self, db_path: Path, candidate_count: int = 2) -> None:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        conn.execute(
            """
            insert into sessions (id, external_id, display_name)
            values (1, 'wxid_secret', 'SECRET_SESSION')
            """
        )
        conn.execute(
            """
            insert into collection_runs (
              id, mode, started_at, finished_at, status, raw_messages_seen,
              raw_messages_inserted, raw_messages_duplicated, candidate_items_created
            )
            values (
              1, 'real', '2026-05-18T10:50:00+08:00',
              '2026-05-18T10:51:00+08:00', 'success', ?, ?, 0, ?
            )
            """,
            (candidate_count, candidate_count, candidate_count),
        )
        for index in range(candidate_count):
            conn.execute(
                """
                insert into raw_messages (
                  id, session_id, sender_display_name, sender_role, sent_at,
                  message_type, content_text, content_hash, dedupe_key,
                  raw_payload_json, collection_run_id
                )
                values (
                  ?, 1, ?, ?, '2026-05-18T10:50:00+08:00',
                  'text', ?, ?, ?, ?, 1
                )
                """,
                (
                    index + 1,
                    "wxid_secret_sender" if index == 0 else "本地显示名",
                    "unknown" if index == 0 else "customer",
                    f"SECRET_BODY_{index}",
                    f"hash-{index}",
                    f"dedupe-{index}",
                    '{"secret":"SECRET_BODY"}',
                ),
            )
            conn.execute(
                """
                insert into candidate_items (
                  item_code, item_type, status, risk_level, risk_tags_json,
                  title, summary, suggested_downstream, aggregate_key,
                  first_seen_at, last_seen_at
                )
                values (
              ?, 'requirement', 'pending', 'none', '[]',
              'SECRET_TITLE', 'SECRET_SUMMARY', 'product', ?,
              '2026-05-18T10:50:00+08:00', '2026-05-18T10:50:00+08:00'
            )
            """,
                (f"R-{index + 1:03d}", f"agg-{index + 1}"),
            )
        conn.execute(
            """
            update candidate_items
            set item_type = 'bug', status = 'confirmed', risk_level = 'high', risk_tags_json = '["SECRET_RISK"]',
                suggested_downstream = 'tech', aggregate_key = 'agg-last'
            where id = (select max(id) from candidate_items)
            """
        )
        link_rows = []
        if candidate_count >= 1:
            link_rows.append((1, 1, 1))
        if candidate_count >= 2:
            link_rows.append((1, 2, 2))
        for raw_id in range(2, candidate_count + 1):
            link_rows.append((raw_id, raw_id, 1))
        conn.executemany(
            """
            insert into candidate_item_messages (item_id, raw_message_id, evidence_order)
            values (?, ?, ?)
            """,
            link_rows,
        )
        conn.commit()
        conn.close()

    def _inject_visible_wxid_candidate_text(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            update candidate_items
            set title = ?,
                summary = ?
            where id = 1
            """,
            (
                "人工构造候选 wxid_synthetic_visible_title",
                "人工构造摘要 wxid_synthetic_visible_summary 需要进入脱敏占位",
            ),
        )
        conn.commit()
        conn.close()
