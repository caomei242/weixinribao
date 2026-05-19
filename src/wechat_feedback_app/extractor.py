from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .config import AppConfig, SessionConfig


@dataclass
class CandidateDraft:
    item_type: str
    risk_level: str
    risk_tags: list[str]
    customer_name: str
    channel_name: str
    module_name: str
    title: str
    summary: str
    suggested_downstream: str
    aggregate_key: str
    first_seen_at: str
    last_seen_at: str


TYPE_RULES: list[tuple[str, str, str, list[str]]] = [
    ("bug", "tech", "疑似问题", ["报错", "登录不了", "转圈", "异常", "不行", "无法", "bug"]),
    ("requirement", "product", "客户需求", ["需求", "能不能", "希望", "建议", "新增", "增加", "调整", "想看"]),
    ("followup", "ops", "待我方跟进", ["明天", "回复", "跟进", "确认一下", "给客户"]),
    ("conclusion", "manual", "沟通结论", ["已确认", "达成一致", "就这么定", "按这个执行"]),
    ("consultation", "ops", "客户咨询", ["咨询", "怎么", "在哪里", "如何", "能否", "吗", "？", "?"]),
]


def extract_candidate(
    message: dict[str, str], session: SessionConfig, config: AppConfig
) -> CandidateDraft | None:
    content = normalize_text(message.get("content_text", ""))
    if not content:
        return None

    item_type, downstream, label = classify(content)
    if item_type is None:
        return None

    risk_tags = detect_risk_tags(content, config)
    risk_level = "high" if risk_tags else "none"
    if risk_tags and "需对外回复" in risk_tags:
        item_type = "followup"
        downstream = "ops"
        label = "待我方跟进"

    title = make_title(content)
    summary = f"{label}：{title}"
    aggregate_base = "|".join(
        [
            item_type,
            session.customer_name,
            session.channel_name,
            session.module_name,
            title,
        ]
    )
    aggregate_key = hashlib.sha256(aggregate_base.encode("utf-8")).hexdigest()

    return CandidateDraft(
        item_type=item_type,
        risk_level=risk_level,
        risk_tags=risk_tags,
        customer_name=session.customer_name,
        channel_name=session.channel_name,
        module_name=session.module_name,
        title=title,
        summary=summary,
        suggested_downstream=downstream,
        aggregate_key=aggregate_key,
        first_seen_at=message["sent_at"],
        last_seen_at=message["sent_at"],
    )


def classify(content: str) -> tuple[str | None, str, str]:
    for item_type, downstream, label, keywords in TYPE_RULES:
        if any(keyword.lower() in content.lower() for keyword in keywords):
            return item_type, downstream, label
    return None, "manual", "待人工判断"


def detect_risk_tags(content: str, config: AppConfig) -> list[str]:
    tags: list[str] = []
    for keyword in config.risk.keywords:
        if keyword and keyword in content:
            if keyword == "回复":
                tag = "需对外回复"
            else:
                tag = keyword
            if tag not in tags:
                tags.append(tag)
    for keyword in config.risk.sensitive_keywords:
        if keyword and keyword in content and "敏感信息" not in tags:
            tags.append("敏感信息")
    return tags


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def make_title(content: str) -> str:
    return content[:48]


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()


def dedupe_key_for_message(message: dict[str, str]) -> str:
    session_id = message["session_external_id"]
    if message.get("message_external_id"):
        return f"{session_id}:message:{message['message_external_id']}"
    if message.get("local_id"):
        return f"{session_id}:local:{message['local_id']}"
    digest = content_hash(message.get("content_text", ""))
    return ":".join(
        [
            session_id,
            "fallback",
            message.get("sent_at", ""),
            message.get("sender_display_name", ""),
            digest,
        ]
    )
