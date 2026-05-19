import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.config import AppConfig, ExportConfig
from wechat_feedback_app.daily_control import (
    apply_daily_control_action,
    daily_control_summary,
    generate_settlement_draft,
    save_quality_feedback,
)
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.routes import (
    daily_control_payload,
    draft_report_preview_payload,
    regenerate_draft_report_payload,
)


class DailyControlTest(unittest.TestCase):
    def test_summary_counts_cards_timeline_and_redacted_pending_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            pending_id = self._insert_candidate(conn, "R-001", "pending", "high")
            self._insert_candidate(conn, "F-001", "confirmed", "none")
            self._insert_candidate(conn, "B-001", "rejected", "low")
            conn.execute(
                """
                insert into collection_runs (
                  mode, started_at, finished_at, status, sessions_total,
                  sessions_success, sessions_failed, raw_messages_seen,
                  raw_messages_inserted, raw_messages_duplicated,
                  candidate_items_created, error_code
                )
                values (
                  'fixture', '2026-05-18T09:00:00+08:00',
                  '2026-05-18T09:01:00+08:00', 'partial_failed',
                  3, 2, 1, 9, 5, 4, 3, 'timeout'
                )
                """
            )
            conn.commit()

            summary = daily_control_summary(config, conn, "2026-05-18")

            self.assertEqual(summary["top_status"]["collection_status"], "partial_failed")
            self.assertEqual(summary["top_status"]["candidate_count"], 3)
            self.assertEqual(summary["top_status"]["pending_count"], 1)
            self.assertEqual(summary["top_status"]["settlement_ready_count"], 1)
            self.assertEqual(summary["top_status"]["rule_feedback_count"], 0)
            self.assertEqual({card["key"] for card in summary["cards"]}, {"collection", "review", "settlement", "quality"})
            self.assertEqual(summary["pending_items"][0]["id"], pending_id)
            self.assertEqual(summary["pending_items"][0]["risk_level"], "high")
            self.assertEqual(summary["timeline"][0]["status"], "partial_failed")
            self.assertEqual(summary["timeline"][0]["error_code"], "timeout")
            text = json.dumps(summary, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)

    def test_item_actions_update_status_type_risk_and_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            item_id = self._insert_candidate(conn, "R-001", "pending", "none")

            result = apply_daily_control_action(
                conn,
                item_id,
                {
                    "review_status": "confirmed",
                    "item_type": "bug",
                    "risk_level": "high",
                    "risk_tags": ["需复核"],
                    "owner_name": "本地负责人",
                    "downstream": "tech",
                    "priority": "P1",
                },
            )
            summary = daily_control_summary(config, conn, "2026-05-18")

            row = conn.execute("select * from candidate_items where id = ?", (item_id,)).fetchone()
            review = conn.execute(
                "select * from manual_reviews where item_id = ? order by id desc limit 1",
                (item_id,),
            ).fetchone()
            self.assertEqual(result["status"], "updated")
            self.assertEqual(row["status"], "confirmed")
            self.assertEqual(row["item_type"], "bug")
            self.assertEqual(row["risk_level"], "high")
            self.assertEqual(json.loads(row["risk_tags_json"]), ["需复核"])
            self.assertEqual(review["owner_name"], "本地负责人")
            self.assertEqual(review["downstream"], "tech")
            self.assertEqual(summary["top_status"]["pending_count"], 0)

    def test_quality_feedback_is_saved_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            item_id = self._insert_candidate(conn, "R-001", "pending", "none")

            result = save_quality_feedback(
                conn,
                "2026-05-18",
                {
                    "item_id": item_id,
                    "feedback_type": "false_positive",
                    "note": "本地规则反馈",
                    "from_type": "requirement",
                    "to_type": "consultation",
                },
            )
            summary = daily_control_summary(config, conn, "2026-05-18")

            self.assertEqual(result["status"], "saved")
            self.assertEqual(summary["quality_feedback"]["counts"]["false_positive"], 1)
            self.assertEqual(summary["top_status"]["rule_feedback_count"], 1)

    def test_generates_local_settlement_draft_without_formal_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            item_id = self._insert_candidate(conn, "F-001", "confirmed", "none")
            apply_daily_control_action(
                conn,
                item_id,
                {
                    "review_status": "confirmed",
                    "owner_name": "本地负责人",
                    "downstream": "product",
                    "priority": "P2",
                },
            )

            result = generate_settlement_draft(config, conn, "2026-05-18")
            summary = daily_control_summary(config, conn, "2026-05-18")

            draft_path = Path(result["file_path"])
            self.assertEqual(result["status"], "generated")
            self.assertTrue(draft_path.exists())
            self.assertIn("daily_control_drafts", draft_path.as_posix())
            self.assertFalse(result["formal_write_enabled"])
            self.assertFalse(summary["settlement_check"]["formal_write_enabled"])
            self.assertTrue(summary["settlement_check"]["draft_generated"])
            text = draft_path.read_text(encoding="utf-8")
            self.assertIn("待沉淀草稿", text)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)

    def test_draft_report_preview_returns_machine_draft_metadata_without_formal_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            item_id = self._insert_candidate(conn, "F-001", "confirmed", "none")

            payload = draft_report_preview_payload(
                config,
                conn,
                {"control_date": "2026-05-18", "data_source": "workspace"},
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["draft_status"], "机器初稿 / 待审阅")
            self.assertEqual(payload["data_source"], "workspace")
            self.assertEqual(payload["candidate_count"], 1)
            self.assertEqual(payload["risk_count"], 0)
            self.assertFalse(payload["formal_write_enabled"])
            self.assertEqual(payload["formal_write_status"], "禁用 / 未写入")
            self.assertEqual(payload["items"][0]["item_id"], item_id)
            self.assertEqual(payload["items"][0]["target"], "workspace_candidate")
            self.assertIn("preview_markdown", payload)
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)
            self.assertNotIn("wxid_secret", text)

    def test_draft_preview_uses_latest_trial_when_workspace_empty_and_trial_has_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(root)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_real_trial_db(trial_db, candidate_count=3)

            payload = draft_report_preview_payload(
                config,
                conn,
                {"control_date": "2026-05-18"},
            )

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["data_source"], "real_trial")
            self.assertEqual(payload["data_source_label"], "最近试读候选")
            self.assertTrue(payload["suggested_from_trial"])
            self.assertEqual(payload["candidate_count"], 3)
            self.assertIn("发现最近试读", payload["next_step"])
            self.assertFalse(payload["formal_write_enabled"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_SENDER", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)

    def test_regenerate_draft_report_writes_only_local_preview_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, conn = self._setup_db(Path(tmp))
            self._insert_candidate(conn, "F-001", "confirmed", "none")

            payload = regenerate_draft_report_payload(
                config,
                conn,
                {"control_date": "2026-05-18", "data_source": "workspace"},
            )

            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["local_preview_saved"])
            self.assertFalse(payload["formal_write_enabled"])
            self.assertEqual(payload["formal_write_status"], "禁用 / 未写入")
            self.assertEqual(
                conn.execute("select count(*) from settlement_drafts").fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("select count(*) from export_records").fetchone()[0],
                0,
            )
            self.assertNotIn(str(Path(tmp)), json.dumps(payload, ensure_ascii=False))

    def test_static_page_exposes_daily_control_dashboard(self):
        root = Path(__file__).resolve().parents[1]
        index_html = (root / "src" / "wechat_feedback_app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        app_js = (root / "src" / "wechat_feedback_app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("dailyControlBtn", index_html)
        self.assertIn("dailyControlDashboard", index_html)
        self.assertIn("writeFormalBtn", index_html)
        self.assertIn("disabled", index_html)
        self.assertIn("/api/daily-control", app_js)
        self.assertIn("/api/daily-control/draft", app_js)
        self.assertIn("/api/daily-control/feedback", app_js)
        self.assertIn("renderDailyControl", app_js)
        self.assertIn("draftReportPanel", index_html)
        self.assertIn("draftReportPreview", index_html)
        self.assertIn("/api/daily-control/draft-preview", app_js)
        self.assertIn("refreshDraftReportPreview", app_js)
        self.assertIn("regenerateDraftReport", app_js)
        self.assertIn("openDraftLinkedItem", app_js)

    def test_daily_control_exposes_real_trial_summary_when_main_pool_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, conn = self._setup_db(root)
            trial_db = root / "data" / "real_trial_recent50_20260518-105050.sqlite3"
            trial_db.parent.mkdir(parents=True, exist_ok=True)
            self._write_real_trial_db(trial_db, candidate_count=3)

            payload = daily_control_payload(config, conn, "2026-05-18")

            self.assertEqual(payload["top_status"]["candidate_count"], 0)
            self.assertEqual(payload["real_trial"]["status"], "ok")
            self.assertEqual(payload["real_trial"]["raw_count"], 3)
            self.assertEqual(payload["real_trial"]["candidate_count"], 3)
            self.assertEqual(payload["real_trial"]["risk_count"], 0)
            self.assertEqual(payload["real_trial_items"]["count"], 3)
            self.assertTrue(payload["real_trial_notice"]["visible"])
            self.assertIn("尚未合并进主工作台", payload["real_trial_notice"]["message"])
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("SECRET_BODY", text)
            self.assertNotIn("SECRET_SENDER", text)
            self.assertNotIn("wxid_secret", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("content_text", text)
            self.assertNotIn("raw_payload_json", text)

    def test_static_daily_control_renders_real_trial_visibility(self):
        root = Path(__file__).resolve().parents[1]
        index_html = (root / "src" / "wechat_feedback_app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )
        app_js = (root / "src" / "wechat_feedback_app" / "static" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("dailyRealTrialPanel", index_html)
        self.assertIn("dailyRealTrialLine", index_html)
        self.assertIn("dailyRealTrialItems", index_html)
        self.assertIn("renderDailyRealTrial", app_js)
        self.assertIn("当前主工作台无待确认事项", app_js)
        self.assertIn("setItemSource(\"realTrial\")", app_js)

    def _setup_db(self, root: Path):
        config = AppConfig(root=root, export=ExportConfig(directory=str(root / "exports")))
        db_path = root / "data" / "test.sqlite3"
        conn = connect(db_path)
        init_db(conn)
        return config, conn

    def _insert_candidate(
        self,
        conn: sqlite3.Connection,
        item_code: str,
        status: str,
        risk_level: str,
    ) -> int:
        cursor = conn.execute(
            """
            insert into candidate_items (
              item_code, item_type, status, risk_level, risk_tags_json,
              customer_name, channel_name, module_name, title, summary,
              suggested_downstream, aggregate_key, first_seen_at, last_seen_at
            )
            values (?, 'requirement', ?, ?, ?, '本地客户', '', '订单',
                    ?, '本地候选摘要', 'product', ?, '2026-05-18T10:00:00+08:00',
                    '2026-05-18T10:00:00+08:00')
            """,
            (
                item_code,
                status,
                risk_level,
                json.dumps(["需复核"] if risk_level != "none" else [], ensure_ascii=False),
                f"{item_code} 本地候选标题",
                f"agg-{item_code}",
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)

    def _write_real_trial_db(self, db_path: Path, candidate_count: int) -> None:
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
              '2026-05-18T10:51:00+08:00', 'success',
              ?, ?, 0, ?
            )
            """,
            (candidate_count, candidate_count, candidate_count),
        )
        for index in range(candidate_count):
            raw_id = index + 1
            conn.execute(
                """
                insert into raw_messages (
                  id, session_id, sender_display_name, sender_role, sent_at,
                  message_type, content_text, content_hash, dedupe_key,
                  raw_payload_json, collection_run_id
                )
                values (?, 1, 'SECRET_SENDER', 'customer',
                        '2026-05-18T10:50:00+08:00', 'text',
                        'SECRET_BODY', ?, ?, '{"secret": true}', 1)
                """,
                (raw_id, f"hash-{raw_id}", f"dedupe-{raw_id}"),
            )
            conn.execute(
                """
                insert into candidate_items (
                  id, item_code, item_type, status, risk_level, risk_tags_json,
                  customer_name, channel_name, module_name, title, summary,
                  suggested_downstream, aggregate_key, first_seen_at, last_seen_at
                )
                values (?, ?, 'requirement', 'pending', 'none', '[]',
                        '本地客户', '', '订单', ?, ?,
                        'product', ?, '2026-05-18T10:50:00+08:00',
                        '2026-05-18T10:50:00+08:00')
                """,
                (
                    raw_id,
                    f"R-{raw_id:03d}",
                    f"试读候选标题 {raw_id}",
                    f"试读候选摘要 {raw_id}",
                    f"trial-agg-{raw_id}",
                ),
            )
            conn.execute(
                """
                insert into candidate_item_messages (item_id, raw_message_id, evidence_order)
                values (?, ?, 1)
                """,
                (raw_id, raw_id),
            )
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main()
