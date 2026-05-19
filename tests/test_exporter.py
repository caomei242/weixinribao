import tempfile
import unittest
from pathlib import Path

from wechat_feedback_app.collector import collect_fixture_messages
from wechat_feedback_app.config import load_config
from wechat_feedback_app.db import connect, init_db
from wechat_feedback_app.exporter import (
    export_all_markdown_templates,
    export_feedback_report,
    export_followup_list,
    export_markdown_template,
    preview_markdown_template,
)


class ExporterTest(unittest.TestCase):
    def test_exports_feedback_report_and_followup_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")

            conn = connect(config.database.path)
            init_db(conn)
            collect_fixture_messages(config, conn)

            conn.execute(
                """
                update candidate_items
                set status = 'confirmed'
                where item_type = 'followup'
                """
            )
            conn.commit()

            report = export_feedback_report(config, conn, "2026-05-15")
            followup = export_followup_list(config, conn, "2026-05-15")

            report_text = Path(report.file_path).read_text(encoding="utf-8")
            followup_text = Path(followup.file_path).read_text(encoding="utf-8")

            self.assertIn("# 2026-05-15 微信反馈日报", report_text)
            self.assertIn("## 运行概览", report_text)
            self.assertIn("## 客户需求", report_text)
            self.assertIn("## 风险项 / 待人工确认", report_text)
            self.assertIn("> 能不能在订单列表直接看到预计发货时间？", report_text)
            self.assertIn("# 2026-05-15 待跟进事项", followup_text)
            self.assertIn("## 今日必须跟进", followup_text)
            self.assertIn("## 需要你确认的风险项", followup_text)
            self.assertTrue(Path(report.file_path).exists())
            self.assertTrue(Path(followup.file_path).exists())

    def test_exports_three_layered_markdown_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")

            conn = connect(config.database.path)
            init_db(conn)
            collect_fixture_messages(config, conn)
            followup_id = conn.execute(
                "select id from candidate_items where item_type = 'followup' limit 1"
            ).fetchone()["id"]
            conn.execute(
                """
                update candidate_items
                set status = 'confirmed'
                where id = ?
                """,
                (followup_id,),
            )
            conn.execute(
                """
                insert into manual_reviews (
                  item_id, review_status, owner_name, priority, downstream, note
                )
                values (?, 'confirmed', '王五', 'P1', 'ops', '本地确认')
                """,
                (followup_id,),
            )
            requirement_id = conn.execute(
                "select id from candidate_items where item_type = 'requirement' limit 1"
            ).fetchone()["id"]
            conn.execute(
                """
                update candidate_items
                set summary = ?,
                    title = ?
                where id = ?
                """,
                (
                    "客户需求：请看 /Users/gd/Desktop/微信agent专项/data/private.sqlite3 和 C:\\Users\\gd\\secret\\db.sqlite3",
                    "路径脱敏测试",
                    requirement_id,
                ),
            )
            risk_id = conn.execute(
                "select id from candidate_items where risk_level != 'none' limit 1"
            ).fetchone()["id"]
            conn.execute(
                """
                update candidate_items
                set summary = ?,
                    title = ?
                where id = ?
                """,
                (
                    "报价合同投诉细节 SECRET_CONTRACT_DETAIL 只允许留在本地审阅",
                    "风险细节",
                    risk_id,
                ),
            )
            conn.commit()

            review = export_markdown_template(config, conn, "2026-05-15", "daily_review")
            followups = export_markdown_template(
                config, conn, "2026-05-15", "followup_checklist"
            )
            transfer = export_markdown_template(
                config, conn, "2026-05-15", "product_tech_summary"
            )

            review_text = Path(review.file_path).read_text(encoding="utf-8")
            followup_text = Path(followups.file_path).read_text(encoding="utf-8")
            transfer_text = Path(transfer.file_path).read_text(encoding="utf-8")

            self.assertIn("# 2026-05-15 微信反馈日报（待审阅）", review_text)
            self.assertIn("## 2. 需要你先确认", review_text)
            self.assertIn("### 客户需求", review_text)
            self.assertIn("### 问题 / Bug", review_text)
            self.assertIn("### 咨询", review_text)
            self.assertIn("### 沟通结论", review_text)
            self.assertIn("### 待我方跟进", review_text)
            self.assertIn("系统初判", review_text)
            self.assertIn("需人工确认", review_text)
            self.assertIn("已确认可转交", review_text)
            self.assertIn("风险不可外发", review_text)
            self.assertIn("## 3. 今日可转交摘要", review_text)
            self.assertIn("## 4. 下游转交摘要", review_text)

            self.assertIn("# 2026-05-15 待跟进事项清单", followup_text)
            self.assertIn("## 今日必须处理", followup_text)
            self.assertIn("## 需要对外回复", followup_text)
            self.assertIn("## 待分派", followup_text)
            self.assertIn("## 已确认但可后置", followup_text)
            self.assertIn("负责人", followup_text)
            self.assertIn("优先级", followup_text)
            self.assertIn("截止时间", followup_text)
            self.assertIn("下游同步对象", followup_text)
            self.assertIn("是否需要对外回复", followup_text)
            self.assertIn("待办池候选，不是正式待办", followup_text)

            self.assertIn("# 2026-05-15 可转产品 / 技术摘要", transfer_text)
            self.assertIn("影响范围", transfer_text)
            self.assertIn("建议优先级", transfer_text)
            self.assertIn("待确认问题", transfer_text)
            self.assertIn("已确认可转交", transfer_text)
            self.assertNotIn("原文证据", transfer_text)
            self.assertNotIn("> 能不能在订单列表直接看到预计发货时间？", transfer_text)
            self.assertNotIn("wxid_", transfer_text)
            self.assertNotIn("key", transfer_text.lower())
            self.assertNotIn("salt", transfer_text.lower())
            self.assertNotIn("daemon", transfer_text.lower())
            self.assertNotIn("raw_payload_json", transfer_text)
            self.assertNotIn("content_text", transfer_text)
            self.assertNotIn("13800000000", transfer_text)
            self.assertNotIn("/Users/gd/Desktop/微信agent专项", transfer_text)
            self.assertNotIn("C:\\Users\\gd", transfer_text)
            self.assertNotIn("SECRET_CONTRACT_DETAIL", transfer_text)

            self.assertTrue(Path(review.file_path).exists())
            self.assertTrue(Path(followups.file_path).exists())
            self.assertTrue(Path(transfer.file_path).exists())
            self.assertIn("exports", Path(transfer.file_path).as_posix())

    def test_preview_and_export_all_markdown_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(root / "data" / "test.sqlite3")
            config.wx_cli.fixture_dir = str(Path.cwd() / "fixtures")
            config.export.directory = str(root / "exports")

            conn = connect(config.database.path)
            init_db(conn)
            collect_fixture_messages(config, conn)

            preview = preview_markdown_template(
                config,
                conn,
                "2026-05-15",
                "product_tech_summary",
                include_pending=True,
                confirmed_only=False,
                separate_risks=True,
            )
            self.assertEqual(preview["status"], "ok")
            self.assertEqual(preview["template_id"], "product_tech_summary")
            self.assertIn("可转产品 / 技术摘要", preview["markdown"])
            self.assertIn("本地 Markdown，不写正式待办池 / 正式日报", preview["safety_boundary"])
            self.assertTrue(preview["filename"].endswith("可转产品技术摘要.md"))

            all_exports = export_all_markdown_templates(config, conn, "2026-05-15")
            self.assertEqual(all_exports["status"], "ok")
            self.assertEqual(len(all_exports["results"]), 3)
            self.assertEqual(
                {item["template_id"] for item in all_exports["results"]},
                {"daily_review", "followup_checklist", "product_tech_summary"},
            )
            for result in all_exports["results"]:
                self.assertTrue(Path(result["file_path"]).exists())
                self.assertIn("本地 Markdown", result["message"])

    def test_static_page_exposes_export_template_center(self):
        root = Path(__file__).resolve().parents[1]
        index_html = (
            root / "src" / "wechat_feedback_app" / "static" / "index.html"
        ).read_text(encoding="utf-8")
        app_js = (
            root / "src" / "wechat_feedback_app" / "static" / "app.js"
        ).read_text(encoding="utf-8")

        self.assertIn("exportTemplateBtn", index_html)
        self.assertIn('<button id="exportTemplateBtn">转述摘要</button>', index_html)
        self.assertNotIn('<button id="exportTemplateBtn">导出模板</button>', index_html)
        self.assertIn("exportTemplateDialog", index_html)
        self.assertIn("templateSelect", index_html)
        self.assertIn("exportTemplatePreview", index_html)
        self.assertIn("exportFilenamePreview", index_html)
        self.assertIn("只生成本机摘要和本机文件", index_html)
        self.assertIn("不会自动写入正式日报", index_html)
        self.assertIn("/api/export/templates/preview", app_js)
        self.assertIn("/api/export/templates", app_js)
        self.assertIn("生成全部文件", index_html)

    def test_export_records_legacy_schema_migration_keeps_old_records_and_allows_new_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "legacy.sqlite3"
            config = load_config(Path("config/app.example.yaml"), root=root)
            config.database.path = str(db_path)
            config.export.directory = str(root / "exports")

            conn = connect(db_path)
            conn.execute(
                """
                create table export_records (
                  id integer primary key autoincrement,
                  export_date text not null,
                  export_type text not null check(export_type in ('feedback_report', 'followup_list')),
                  file_path text not null,
                  filters_json text not null default '{}',
                  item_ids_json text not null default '[]',
                  template_version text not null,
                  generated_at text not null default current_timestamp
                )
                """
            )
            conn.execute(
                """
                insert into export_records (
                  export_date, export_type, file_path, filters_json, item_ids_json, template_version
                )
                values ('2026-05-14', 'feedback_report', 'exports/old.md', '{}', '[1]', 'fixture-v1')
                """
            )
            conn.commit()

            init_db(conn)
            export_markdown_template(config, conn, "2026-05-15", "product_tech_summary")

            rows = conn.execute(
                "select export_date, export_type, file_path from export_records order by id"
            ).fetchall()
            self.assertEqual(rows[0]["export_date"], "2026-05-14")
            self.assertEqual(rows[0]["export_type"], "feedback_report")
            self.assertEqual(rows[0]["file_path"], "exports/old.md")
            self.assertEqual(rows[1]["export_type"], "product_tech_summary")


if __name__ == "__main__":
    unittest.main()
