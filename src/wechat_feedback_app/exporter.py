from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig, resolve_path


TEMPLATE_VERSION = "markdown-template-v1"

TEMPLATE_DEFINITIONS = {
    "daily_review": {
        "name": "每日反馈日报（审阅版）",
        "filename_suffix": "微信反馈日报（审阅版）.md",
        "export_type": "daily_review",
    },
    "followup_checklist": {
        "name": "待跟进事项清单",
        "filename_suffix": "待跟进事项清单.md",
        "export_type": "followup_checklist",
    },
    "product_tech_summary": {
        "name": "可转产品 / 技术摘要",
        "filename_suffix": "可转产品技术摘要.md",
        "export_type": "product_tech_summary",
    },
}

DEFAULT_TEMPLATE_IDS = [
    "daily_review",
    "followup_checklist",
    "product_tech_summary",
]


@dataclass
class ExportResult:
    export_type: str
    export_date: str
    file_path: str
    item_ids: list[int]


@dataclass
class MarkdownTemplateResult:
    template_id: str
    template_name: str
    export_date: str
    file_path: str
    item_ids: list[int]
    message: str


def export_feedback_report(
    config: AppConfig, conn: sqlite3.Connection, export_date: str
) -> ExportResult:
    items = load_items_for_date(conn, export_date, include_rejected=False)
    overview = load_overview(conn)
    lines = [f"# {export_date} 微信反馈日报", "", "## 运行概览", ""]
    lines.extend(
        [
            f"- 采集时间：{overview.get('started_at', '未采集')} - {overview.get('finished_at', '未完成')}",
            f"- 白名单会话：{overview.get('sessions_total', 0)} 个",
            f"- 成功采集：{overview.get('sessions_success', 0)} 个",
            f"- 采集失败：{overview.get('sessions_failed', 0)} 个",
            f"- 新增原始消息：{overview.get('raw_messages_inserted', 0)} 条",
            f"- 结构化候选事项：{len(items)} 条",
            f"- 需要人工确认：{sum(1 for item in items if item['status'] == 'pending')} 条",
            "",
        ]
    )

    sections = [
        ("客户需求", "requirement"),
        ("问题 / Bug", "bug"),
        ("咨询", "consultation"),
        ("沟通结论", "conclusion"),
        ("待我方跟进", "followup"),
    ]
    for title, item_type in sections:
        lines.extend([f"## {title}", ""])
        section_items = [item for item in items if item["item_type"] == item_type]
        if not section_items:
            lines.extend(["暂无", ""])
            continue
        for item in section_items:
            lines.extend(render_item_block(item))

    risk_items = [item for item in items if item["risk_level"] != "none"]
    lines.extend(["## 风险项 / 待人工确认", ""])
    if not risk_items:
        lines.extend(["暂无", ""])
    else:
        for item in risk_items:
            lines.extend(render_item_block(item))

    return write_export(
        config,
        conn,
        export_date,
        "feedback_report",
        f"{export_date} 微信反馈日报.md",
        lines,
        [int(item["id"]) for item in items],
    )


def export_followup_list(
    config: AppConfig, conn: sqlite3.Connection, export_date: str
) -> ExportResult:
    items = load_items_for_date(conn, export_date, include_rejected=False)
    followups = [
        item
        for item in items
        if item["status"] == "confirmed"
        or item["item_type"] == "followup"
        or item["risk_level"] == "high"
    ]
    risk_items = [item for item in items if item["risk_level"] != "none"]
    lines = [f"# {export_date} 待跟进事项", "", "## 今日必须跟进", ""]
    if not followups:
        lines.extend(["暂无", ""])
    else:
        for item in followups:
            lines.extend(
                [
                    f"- [ ] {item['item_code']}｜{party_name(item)}｜{item['title']}",
                    f"  - 负责人：{latest_review(item).get('owner_name', '')}",
                    f"  - 优先级：{latest_review(item).get('priority', 'P2')}",
                    f"  - 下游同步：{latest_review(item).get('downstream', item['suggested_downstream'])}",
                    "  - 截止时间：",
                    "",
                ]
            )
    lines.extend(["## 需要你确认的风险项", ""])
    if not risk_items:
        lines.extend(["暂无", ""])
    else:
        for item in risk_items:
            tags = "、".join(item["risk_tags"])
            lines.append(f"- [ ] {item['item_code']}｜{party_name(item)}｜{tags}｜{item['title']}")
        lines.append("")

    return write_export(
        config,
        conn,
        export_date,
        "followup_list",
        f"{export_date} 待跟进事项.md",
        lines,
        [int(item["id"]) for item in followups],
    )


def preview_markdown_template(
    config: AppConfig,
    conn: sqlite3.Connection,
    export_date: str,
    template_id: str,
    *,
    include_pending: bool = True,
    confirmed_only: bool = False,
    separate_risks: bool = True,
    source_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    template = template_definition(template_id)
    items = load_template_items(
        conn,
        export_date,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
        source_items=source_items,
    )
    lines = render_template_lines(
        template_id,
        export_date,
        items,
        separate_risks=separate_risks,
    )
    filename = template_filename(export_date, template_id)
    return {
        "status": "ok",
        "template_id": template_id,
        "template_name": template["name"],
        "export_date": export_date,
        "filename": filename,
        "markdown": "\n".join(lines).rstrip() + "\n",
        "item_count": len(items),
        "risk_count": len(risk_items(items)),
        "safety_boundary": "本地 Markdown，不写正式待办池 / 正式日报 / Obsidian 正式区或外部系统。",
        "formal_write_enabled": False,
    }


def export_markdown_template(
    config: AppConfig,
    conn: sqlite3.Connection,
    export_date: str,
    template_id: str,
    *,
    include_pending: bool = True,
    confirmed_only: bool = False,
    separate_risks: bool = True,
    source_items: list[dict[str, object]] | None = None,
) -> MarkdownTemplateResult:
    template = template_definition(template_id)
    items = load_template_items(
        conn,
        export_date,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
        source_items=source_items,
    )
    lines = render_template_lines(
        template_id,
        export_date,
        items,
        separate_risks=separate_risks,
    )
    result = write_export(
        config,
        conn,
        export_date,
        str(template["export_type"]),
        template_filename(export_date, template_id),
        lines,
        [int(item["id"]) for item in items],
    )
    return MarkdownTemplateResult(
        template_id=template_id,
        template_name=str(template["name"]),
        export_date=export_date,
        file_path=result.file_path,
        item_ids=result.item_ids,
        message="已导出本地 Markdown，不写正式待办池 / 正式日报。",
    )


def export_all_markdown_templates(
    config: AppConfig,
    conn: sqlite3.Connection,
    export_date: str,
    *,
    include_pending: bool = True,
    confirmed_only: bool = False,
    separate_risks: bool = True,
    template_ids: list[str] | None = None,
    source_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    selected = template_ids or DEFAULT_TEMPLATE_IDS
    results = [
        export_markdown_template(
            config,
            conn,
            export_date,
            template_id,
            include_pending=include_pending,
            confirmed_only=confirmed_only,
            separate_risks=separate_risks,
            source_items=source_items,
        ).__dict__
        for template_id in selected
    ]
    return {
        "status": "ok",
        "export_date": export_date,
        "results": results,
        "formal_write_enabled": False,
        "message": "已导出本地 Markdown，不写正式待办池 / 正式日报。",
    }


def load_template_items(
    conn: sqlite3.Connection,
    export_date: str,
    *,
    include_pending: bool,
    confirmed_only: bool,
    source_items: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    items = list(source_items) if source_items is not None else load_items_for_date(conn, export_date, include_rejected=False)
    if confirmed_only:
        return [item for item in items if item["status"] == "confirmed"]
    if not include_pending:
        return [item for item in items if item["status"] != "pending"]
    return items


def render_template_lines(
    template_id: str,
    export_date: str,
    items: list[dict[str, object]],
    *,
    separate_risks: bool,
) -> list[str]:
    if template_id == "daily_review":
        return render_daily_review_template(export_date, items, separate_risks)
    if template_id == "followup_checklist":
        return render_followup_template(export_date, items, separate_risks)
    if template_id == "product_tech_summary":
        return render_product_tech_template(export_date, items, separate_risks)
    raise ValueError(f"unsupported template_id: {template_id}")


def render_daily_review_template(
    export_date: str, items: list[dict[str, object]], separate_risks: bool
) -> list[str]:
    pending_items = [item for item in items if item["status"] == "pending"]
    risks = risk_items(items)
    lines = [
        f"# {export_date} 微信反馈日报（待审阅）",
        "",
        "## 1. 今日概览",
        "",
        "- 模板：每日反馈日报（审阅版）",
        f"- 生成候选：{len(items)}",
        f"- 待确认：{len(pending_items)}",
        f"- 高风险：{len([item for item in risks if item['risk_level'] == 'high'])}",
        "- 模板语义：系统初判 / 需人工确认 / 已确认可转交 / 风险不可外发 / 待办池候选，不是正式待办",
        "- 安全边界：本地 Markdown，不写正式待办池 / 正式日报；审阅版仅供本地人工确认。",
        "",
        "## 2. 需要你先确认",
        "",
    ]
    if not pending_items:
        lines.extend(["暂无", ""])
    else:
        lines.extend(
            [
                "| 编号 | 客户/渠道 | 类型 | 摘要 | 风险 | 建议动作 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in pending_items:
            lines.append(
                "| "
                + " | ".join(
                    [
                        cell(item["item_code"]),
                        cell(party_name(item)),
                        cell(type_label(item["item_type"])),
                        cell(item["summary"]),
                        cell(risk_label(item)),
                        "需人工确认",
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(render_transferable_summary(items))
    lines.extend(render_downstream_summary(items))
    lines.extend(["## 5. 按类型归类", ""])
    for section_title, item_type in item_sections():
        lines.extend([f"### {section_title}", ""])
        section_items = [item for item in items if item["item_type"] == item_type]
        if not section_items:
            lines.extend(["暂无", ""])
            continue
        for item in section_items:
            lines.extend(render_review_item(item))

    if separate_risks:
        lines.extend(render_risk_section(risks))
    return lines


def render_followup_template(
    export_date: str, items: list[dict[str, object]], separate_risks: bool
) -> list[str]:
    lines = [
        f"# {export_date} 待跟进事项清单",
        "",
        "- 模板语义：待办池候选，不是正式待办；需人工确认后再写正式待办池。",
        "- 安全边界：本地 Markdown，不写正式待办池 / 正式日报。",
        "",
        "## 今日必须处理",
        "",
    ]
    layers = followup_layers(items)
    lines.extend(render_followup_table(layers["must_handle"]))
    for title, key in [
        ("需要对外回复", "external_reply"),
        ("待分派", "unassigned"),
        ("已确认但可后置", "confirmed_later"),
    ]:
        lines.extend([f"## {title}", ""])
        lines.extend(render_followup_table(layers[key]))

    if separate_risks:
        lines.extend(render_risk_section(risk_items(items)))
    return lines


def render_product_tech_template(
    export_date: str, items: list[dict[str, object]], separate_risks: bool
) -> list[str]:
    transferable = [
        item
        for item in items
        if item["item_type"] in {"requirement", "bug", "consultation"}
        and item["risk_level"] == "none"
    ]
    confirmed = [item for item in transferable if item["status"] == "confirmed"]
    pending = [item for item in transferable if item["status"] == "pending"]
    lines = [
        f"# {export_date} 可转产品 / 技术摘要",
        "",
        "- 模板语义：已确认可转交优先；待确认项只作为问题线索；风险不可外发。",
        "- 安全边界：不含原始聊天内容、敏感标识、密钥、数据库位置、后台日志或可外泄敏感细节。",
        "- 输出范围：仅本项目本地 Markdown，不写正式区，不外发。",
        "",
        "## 已确认可转交",
        "",
    ]
    lines.extend(render_transfer_table(confirmed))
    lines.extend(["## 待确认问题", ""])
    lines.extend(render_transfer_table(pending))
    if separate_risks:
        risky_count = len(risk_items(items))
        lines.extend(
            [
                "## 风险不可外发",
                "",
                f"- 已排除风险候选：{risky_count} 条",
                "- 处理建议：先由人工复核敏感信息、报价、合同、投诉、金额和对外回复口径。",
                "",
            ]
        )
    return lines


def render_transfer_table(items: list[dict[str, object]]) -> list[str]:
    if not items:
        return ["暂无", ""]
    lines = [
        "| 编号 | 类型 | 可转述摘要 | 影响范围 | 建议优先级 | 待确认问题 |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        review = latest_review(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(item["item_code"]),
                    cell(type_label(item["item_type"])),
                    cell(redact_transfer_text(str(item["summary"]))),
                    cell(redact_transfer_text(impact_scope(item))),
                    cell(review.get("priority", suggested_priority(item))),
                    cell("无" if item["status"] == "confirmed" else "需人工确认口径和影响范围"),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def render_transferable_summary(items: list[dict[str, object]]) -> list[str]:
    transferable = [
        item
        for item in items
        if item["status"] == "confirmed" and item["risk_level"] == "none"
    ]
    lines = ["## 3. 今日可转交摘要", ""]
    if not transferable:
        return lines + ["暂无", ""]
    lines.extend(["| 编号 | 类型 | 摘要 | 建议下游 |", "|---|---|---|---|"])
    for item in transferable:
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(item["item_code"]),
                    cell(type_label(item["item_type"])),
                    cell(item["summary"]),
                    cell(item["suggested_downstream"]),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def render_downstream_summary(items: list[dict[str, object]]) -> list[str]:
    transferable = [
        item
        for item in items
        if item["status"] == "confirmed" and item["risk_level"] == "none"
    ]
    lines = ["## 4. 下游转交摘要", ""]
    for downstream in ["product", "tech", "ops", "manual"]:
        group_items = [item for item in transferable if item["suggested_downstream"] == downstream]
        lines.extend([f"### {downstream_label(downstream)}", ""])
        if not group_items:
            lines.extend(["暂无", ""])
            continue
        for item in group_items:
            lines.append(f"- {item['item_code']}｜{type_label(item['item_type'])}｜{item['summary']}")
        lines.append("")
    return lines


def followup_layers(
    items: list[dict[str, object]]
) -> dict[str, list[dict[str, object]]]:
    selected = [
        item
        for item in items
        if item["status"] == "confirmed"
        or item["item_type"] == "followup"
        or item["risk_level"] != "none"
    ]
    layers = {
        "must_handle": [],
        "external_reply": [],
        "unassigned": [],
        "confirmed_later": [],
    }
    seen: set[int] = set()

    def add(layer: str, item: dict[str, object]) -> None:
        item_id = int(item["id"])
        if item_id not in seen:
            layers[layer].append(item)
            seen.add(item_id)

    for item in selected:
        review = latest_review(item)
        priority = str(review.get("priority", suggested_priority(item)))
        owner = str(review.get("owner_name", "")).strip()
        if priority in {"P0", "P1"} or item["risk_level"] != "none":
            add("must_handle", item)
        elif external_reply_label(item) == "是":
            add("external_reply", item)
        elif not owner:
            add("unassigned", item)
        elif item["status"] == "confirmed":
            add("confirmed_later", item)
        else:
            add("unassigned", item)
    return layers


def render_followup_table(items: list[dict[str, object]]) -> list[str]:
    if not items:
        return ["暂无", ""]
    lines = [
        "| 编号 | 对象 | 摘要 | 负责人 | 优先级 | 截止时间 | 下游同步对象 | 是否需要对外回复 | 状态 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in items:
        review = latest_review(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(item["item_code"]),
                    cell(party_name(item)),
                    cell(item["summary"]),
                    cell(review.get("owner_name", "")),
                    cell(review.get("priority", suggested_priority(item))),
                    cell("待人工确认"),
                    cell(review.get("downstream", item["suggested_downstream"])),
                    cell(external_reply_label(item)),
                    cell(status_semantic(item)),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def render_review_item(item: dict[str, object]) -> list[str]:
    lines = [
        f"#### {item['item_code']}｜{party_name(item)}｜{status_semantic(item)}",
        "",
        f"- 系统初判：{item['summary']}",
        f"- 风险状态：{risk_label(item)}",
        f"- 待办语义：待办池候选，不是正式待办",
        f"- 建议同步：{item['suggested_downstream']}",
        "- 本地证据引用：",
    ]
    for evidence in item["evidence"]:
        lines.append(f"  > {evidence['content_text']}")
    lines.append("")
    return lines


def render_risk_section(items: list[dict[str, object]]) -> list[str]:
    lines = ["## 风险项单独聚合", ""]
    if not items:
        lines.extend(["暂无", ""])
        return lines
    grouped = risk_groups(items)
    for group in ["报价", "合同", "投诉", "金额", "敏感客户信息", "需要对外回复", "其他风险"]:
        group_items = grouped.get(group, [])
        lines.extend([f"### {group}", ""])
        if not group_items:
            lines.extend(["暂无", ""])
            continue
        for item in group_items:
            lines.append(
                f"- {item['item_code']}｜{party_name(item)}｜{status_semantic(item)}｜{item['summary']}"
            )
        lines.append("")
    return lines


def risk_groups(items: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for item in items:
        tags = set(str(tag) for tag in item.get("risk_tags", []))
        matched = False
        mapping = {
            "报价": "报价",
            "合同": "合同",
            "投诉": "投诉",
            "金额": "金额",
            "敏感信息": "敏感客户信息",
            "需对外回复": "需要对外回复",
        }
        for tag, group in mapping.items():
            if tag in tags:
                groups.setdefault(group, []).append(item)
                matched = True
        if not matched:
            groups.setdefault("其他风险", []).append(item)
    return groups


def risk_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return [item for item in items if item["risk_level"] != "none"]


def item_sections() -> list[tuple[str, str]]:
    return [
        ("客户需求", "requirement"),
        ("问题 / Bug", "bug"),
        ("咨询", "consultation"),
        ("沟通结论", "conclusion"),
        ("待我方跟进", "followup"),
    ]


def template_definition(template_id: str) -> dict[str, str]:
    try:
        return TEMPLATE_DEFINITIONS[template_id]
    except KeyError as exc:
        raise ValueError(f"unsupported template_id: {template_id}") from exc


def template_filename(export_date: str, template_id: str) -> str:
    template = template_definition(template_id)
    return f"{export_date} {template['filename_suffix']}"


def status_semantic(item: dict[str, object]) -> str:
    if item["risk_level"] != "none":
        return "风险不可外发"
    if item["status"] == "confirmed":
        return "已确认可转交"
    if item["status"] == "pending":
        return "需人工确认"
    return status_label(item["status"])


def type_label(item_type: object) -> str:
    return {
        "requirement": "客户需求",
        "bug": "问题 / Bug",
        "consultation": "咨询",
        "conclusion": "沟通结论",
        "followup": "待我方跟进",
    }.get(str(item_type), str(item_type))


def downstream_label(downstream: object) -> str:
    return {
        "product": "产品",
        "tech": "技术",
        "ops": "运营",
        "manual": "人工判断",
        "none": "暂不同步",
    }.get(str(downstream), str(downstream))


def risk_label(item: dict[str, object]) -> str:
    if item["risk_level"] == "none":
        return "无风险"
    tags = "、".join(str(tag) for tag in item.get("risk_tags", [])) or str(
        item["risk_level"]
    )
    return f"风险不可外发：{tags}"


def external_reply_label(item: dict[str, object]) -> str:
    tags = set(str(tag) for tag in item.get("risk_tags", []))
    return "是" if "需对外回复" in tags or item["item_type"] == "followup" else "否"


def impact_scope(item: dict[str, object]) -> str:
    parts = [party_name(item)]
    if item.get("module_name"):
        parts.append(str(item["module_name"]))
    parts.append(type_label(item["item_type"]))
    return " / ".join(parts)


def suggested_priority(item: dict[str, object]) -> str:
    if item["risk_level"] == "high":
        return "P1"
    if item["item_type"] == "bug":
        return "P1"
    return "P2"


def redact_visible_text(text: object) -> str:
    redacted = str(text or "")
    redacted = re.sub(r"(?i)wxid[_a-z0-9-]*", "[敏感信息已脱敏]", redacted)
    redacted = re.sub(r"\b1[3-9]\d{9}\b", "[敏感信息已脱敏]", redacted)
    redacted = re.sub(r"\b\d{8,}\b", "[敏感信息已脱敏]", redacted)
    redacted = re.sub(r"(?i)(key|salt|daemon|raw_payload_json|content_text)", "[敏感信息已脱敏]", redacted)
    redacted = re.sub(
        r"(?i)\b[A-Z]:\\(?:[^\\\s|，。；,;]+\\)*[^\\\s|，。；,;]+",
        "[路径已脱敏]",
        redacted,
    )
    redacted = re.sub(
        r"/(?:Users|private|var|tmp|Applications|Volumes)(?:/[^\s|，。；,;]+)+",
        "[路径已脱敏]",
        redacted,
    )
    redacted = re.sub(
        r"(?:^|\s)(?:微信agent专项|data|exports|config|logs)(?:/[^\s|，。；,;]+)+",
        " [路径已脱敏]",
        redacted,
    )
    return redacted


def redact_transfer_text(text: str) -> str:
    return redact_visible_text(text)


def cell(value: object) -> str:
    return str(value or "").replace("\n", " ").replace("|", " / ")


def load_items_for_date(
    conn: sqlite3.Connection, export_date: str, include_rejected: bool = False
) -> list[dict[str, object]]:
    status_clause = "" if include_rejected else "and ci.status != 'rejected'"
    rows = conn.execute(
        f"""
        select ci.*
        from candidate_items ci
        where date(ci.first_seen_at) = date(?)
        {status_clause}
        order by ci.first_seen_at, ci.id
        """,
        (export_date,),
    ).fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["risk_tags"] = json.loads(str(item["risk_tags_json"]))
        item["evidence"] = load_evidence(conn, int(item["id"]))
        item["reviews"] = load_reviews(conn, int(item["id"]))
        items.append(item)
    return items


def load_evidence(conn: sqlite3.Connection, item_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        select rm.*, s.display_name as session_name
        from candidate_item_messages cim
        join raw_messages rm on rm.id = cim.raw_message_id
        join sessions s on s.id = rm.session_id
        where cim.item_id = ?
        order by cim.evidence_order, rm.sent_at
        """,
        (item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_reviews(conn: sqlite3.Connection, item_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        select *
        from manual_reviews
        where item_id = ?
        order by reviewed_at desc, id desc
        """,
        (item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_overview(conn: sqlite3.Connection) -> dict[str, object]:
    row = conn.execute(
        "select * from collection_runs order by id desc limit 1"
    ).fetchone()
    return dict(row) if row else {}


def render_item_block(item: dict[str, object]) -> list[str]:
    risk_tags = "、".join(item["risk_tags"]) if item["risk_tags"] else "无"
    lines = [
        f"### {item['item_code']}｜{party_name(item)}｜{item['module_name'] or '未标模块'}｜{status_label(item['status'])}",
        "",
        f"- 来源会话：{first_evidence(item).get('session_name', '')}",
        f"- 发送方：{first_evidence(item).get('sender_role', '')}",
        "- 原文证据：",
    ]
    for evidence in item["evidence"]:
        lines.append(f"  > {evidence['content_text']}")
    lines.extend(
        [
            f"- 初步判断：{item['summary']}",
            f"- 风险标签：{risk_tags}",
            f"- 建议同步：{item['suggested_downstream']}",
            f"- 状态：{status_label(item['status'])}",
            "- 人工确认：",
            f"  - 负责人：{latest_review(item).get('owner_name', '')}",
            f"  - 优先级：{latest_review(item).get('priority', '')}",
            f"  - 备注：{latest_review(item).get('note', '')}",
            "",
        ]
    )
    return lines


def latest_review(item: dict[str, object]) -> dict[str, object]:
    reviews = item.get("reviews", [])
    return reviews[0] if reviews else {}


def first_evidence(item: dict[str, object]) -> dict[str, object]:
    evidence = item.get("evidence", [])
    return evidence[0] if evidence else {}


def party_name(item: dict[str, object]) -> str:
    return str(item.get("customer_name") or item.get("channel_name") or "未标对象")


def status_label(status: object) -> str:
    return {"pending": "待人工确认", "confirmed": "已确认", "rejected": "已驳回"}.get(
        str(status), str(status)
    )


def write_export(
    config: AppConfig,
    conn: sqlite3.Connection,
    export_date: str,
    export_type: str,
    filename: str,
    lines: list[str],
    item_ids: list[int],
) -> ExportResult:
    export_dir = resolve_path(config.root, config.export.directory) / export_date
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / filename
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    conn.execute(
        """
        insert into export_records (
          export_date, export_type, file_path, filters_json, item_ids_json,
          template_version
        )
        values (?, ?, ?, '{}', ?, ?)
        """,
        (
            export_date,
            export_type,
            str(path),
            json.dumps(item_ids, ensure_ascii=False),
            TEMPLATE_VERSION,
        ),
    )
    conn.commit()
    return ExportResult(export_type, export_date, str(path), item_ids)
