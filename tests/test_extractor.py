import unittest

from wechat_feedback_app.config import AppConfig, RiskConfig, SessionConfig
from wechat_feedback_app.extractor import extract_candidate


class ExtractorTest(unittest.TestCase):
    def test_rule_extractor_classifies_types_and_marks_risks_conservatively(self):
        config = AppConfig(
            sessions=[
                SessionConfig(
                    external_id="customer-a",
                    display_name="客户A项目群",
                    customer_name="客户A",
                    module_name="订单",
                    is_whitelisted=True,
                )
            ],
            risk=RiskConfig(
                keywords=["报价", "合同", "金额", "投诉", "手机号", "回复"],
                sensitive_keywords=["手机号"],
            ),
        )
        session = config.sessions[0]

        requirement = extract_candidate(
            {
                "content_text": "能不能在订单列表直接看到预计发货时间？",
                "sent_at": "2026-05-15T09:00:00+08:00",
                "sender_role": "customer",
            },
            session,
            config,
        )
        bug = extract_candidate(
            {
                "content_text": "今天登录一直转圈，换了浏览器也不行",
                "sent_at": "2026-05-15T09:30:00+08:00",
                "sender_role": "customer",
            },
            session,
            config,
        )
        risky = extract_candidate(
            {
                "content_text": "这个报价和合同金额需要明天回复客户",
                "sent_at": "2026-05-15T10:00:00+08:00",
                "sender_role": "customer",
            },
            session,
            config,
        )

        self.assertEqual(requirement.item_type, "requirement")
        self.assertEqual(requirement.suggested_downstream, "product")
        self.assertEqual(requirement.risk_level, "none")
        self.assertEqual(bug.item_type, "bug")
        self.assertEqual(bug.suggested_downstream, "tech")
        self.assertEqual(risky.item_type, "followup")
        self.assertEqual(risky.risk_level, "high")
        self.assertIn("报价", risky.risk_tags)
        self.assertIn("合同", risky.risk_tags)
        self.assertIn("金额", risky.risk_tags)
        self.assertIn("需对外回复", risky.risk_tags)


if __name__ == "__main__":
    unittest.main()
