import json
import unittest
from pathlib import Path

from wechat_feedback_app.config import (
    TRIAL_SESSION_NAME,
    AppConfig,
    AppSettings,
    CollectorConfig,
    DatabaseConfig,
    ExportConfig,
    RiskConfig,
    SessionConfig,
    WxCliConfig,
)
from wechat_feedback_app.routes import (
    safe_config_payload,
    safe_status_payload,
    safe_wx_cli_public_payload,
)


class RealConnectionRedactionTest(unittest.TestCase):
    def test_status_and_config_do_not_expose_real_session_or_paths(self):
        config = AppConfig(
            app=AppSettings(),
            database=DatabaseConfig(path="/private/db_storage/message.sqlite3"),
            wx_cli=WxCliConfig(
                mode="real",
                binary="/private/wx-cli/target/debug/wx",
                real_read_enabled=False,
                real_allowed_session=TRIAL_SESSION_NAME,
            ),
            collector=CollectorConfig(),
            export=ExportConfig(directory="/private/exports"),
            sessions=[
                SessionConfig(
                    external_id="wxid_sensitive",
                    display_name=TRIAL_SESSION_NAME,
                    customer_name="真实客户名",
                    is_whitelisted=True,
                    enabled=True,
                )
            ],
            risk=RiskConfig(
                keywords=["secret-key-material"],
                sensitive_keywords=["daemon raw log"],
            ),
            root=Path.cwd(),
        )

        for payload in (safe_status_payload(config), safe_config_payload(config)):
            text = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn(TRIAL_SESSION_NAME, text)
            self.assertNotIn("wxid_sensitive", text)
            self.assertNotIn("真实客户名", text)
            self.assertNotIn("/private/", text)
            self.assertNotIn("secret-key-material", text)
            self.assertNotIn("daemon raw log", text)
            self.assertNotIn("real_allowed_session", text)
            self.assertNotIn('"sessions": [', text)

    def test_static_page_uses_redacted_status_and_config_summary(self):
        app_js = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "wechat_feedback_app"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")

        self.assertNotIn("trial.session", app_js)
        self.assertNotIn("binary_path", app_js)
        self.assertNotIn("result.binary_path", app_js)
        self.assertNotIn("ready.binary_path", app_js)
        self.assertNotIn("binary=", app_js)
        self.assertNotIn("JSON.stringify(data, null, 2)", app_js)
        self.assertIn("enabled_whitelist_count", app_js)
        self.assertIn("binaryConfiguredText", app_js)
        self.assertIn("openConfigCenter", app_js)
        self.assertIn("renderConfigCenter", app_js)
        self.assertIn("/api/config-center", app_js)
        self.assertNotIn("renderConfigSummary", app_js)

    def test_wx_cli_public_payload_does_not_return_binary_paths(self):
        payload = safe_wx_cli_public_payload(
            {
                "status": "missing_binary",
                "error_code": "missing_binary",
                "message": "找不到 wx-cli 二进制：/private/wx-cli/bin/wx",
                "binary_path": "/private/wx-cli/bin/wx",
                "configured_binary": "/private/wx-cli/bin/wx",
                "binary_configured": "true",
                "is_executable": "false",
                "session_count": "0",
            }
        )

        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("/private/", text)
        self.assertNotIn('"binary_path":', text)
        self.assertNotIn('"configured_binary":', text)
        self.assertTrue(payload["binary_configured"])
        self.assertFalse(payload["binary_path_returned"])


if __name__ == "__main__":
    unittest.main()
