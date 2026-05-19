from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig, resolve_path


FEEDBACK_TYPES = ("false_positive", "missed", "type_correction", "risk_correction")
ITEM_TYPES = ("requirement", "bug", "consultation", "conclusion", "followup")
RISK_LEVELS = ("none", "low", "high")
REVIEW_STATUSES = ("pending", "confirmed", "rejected")
DOWNSTREAMS = ("product", "tech", "ops", "none")
PRIORITIES = ("P0", "P1", "P2", "P3")


@dataclass
class SettlementDraftResult:
    status: str
    file_path: str
    item_ids: list[int]
    formal_write_enabled: bool = False
    formal_write_reason: str = "formal_path_not_configured"


def daily_control_summary(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    candidates = load_daily_candidate_summaries(conn, control_date)
    pending_items = [item for item in candidates if item["status"] == "pending"]
    confirmed_items = [item for item in candidates if item["status"] == "confirmed"]
    risk_items = [item for item in candidates if item["risk_level"] != "none"]
    latest_run = latest_run_for_date(conn, control_date)
    feedback_counts = quality_feedback_counts(conn, control_date)
    draft = latest_draft_for_date(conn, control_date)
    settlement_check = build_settlement_check(confirmed_items, risk_items, draft)
    collection_status = latest_run.get("status") if latest_run else "未运行"

    top_status = {
        "control_date": control_date,
        "collection_status": collection_status,
        "candidate_count": len(candidates),
        "pending_count": len(pending_items),
        "settlement_ready_count": len(confirmed_items),
        "rule_feedback_count": sum(feedback_counts.values()),
        "error_code": latest_run.get("error_code") if latest_run else "",
        "failed_count": int(latest_run.get("sessions_failed") or 0) if latest_run else 0,
    }
    return {
        "status": "ok",
        "control_date": control_date,
        "top_status": top_status,
        "cards": [
            collection_card(latest_run),
            review_card(pending_items, risk_items),
            settlement_card(confirmed_items, settlement_check),
            quality_card(feedback_counts),
        ],
        "pending_items": pending_items,
        "settlement_check": settlement_check,
        "timeline": build_timeline(latest_run, candidates, feedback_counts, draft),
        "quality_feedback": {
            "counts": feedback_counts,
            "total": sum(feedback_counts.values()),
        },
    }


def apply_daily_control_action(
    conn: sqlite3.Connection, item_id: int, payload: dict[str, Any]
) -> dict[str, Any]:
    row = conn.execute("select * from candidate_items where id = ?", (item_id,)).fetchone()
    if row is None:
        return {"status": "not_found", "item_id": item_id}

    updates: dict[str, Any] = {}
    if payload.get("review_status") in REVIEW_STATUSES:
        updates["status"] = payload["review_status"]
    if payload.get("item_type") in ITEM_TYPES:
        updates["item_type"] = payload["item_type"]
    if payload.get("risk_level") in RISK_LEVELS:
        updates["risk_level"] = payload["risk_level"]
    if "risk_tags" in payload:
        updates["risk_tags_json"] = json.dumps(
            [str(tag).strip() for tag in payload.get("risk_tags", []) if str(tag).strip()],
            ensure_ascii=False,
        )

    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values())
        values.append(item_id)
        conn.execute(
            f"update candidate_items set {assignments}, updated_at = current_timestamp where id = ?",
            values,
        )

    review_status = str(payload.get("review_status") or updates.get("status") or row["status"])
    priority = clean_choice(payload.get("priority"), PRIORITIES, "P2")
    downstream = clean_choice(payload.get("downstream"), DOWNSTREAMS, "none")
    owner_name = clean_text(payload.get("owner_name"))
    note = clean_text(payload.get("note"))
    if any([payload.get("review_status"), owner_name, downstream != "none", note, payload.get("priority")]):
        conn.execute(
            """
            insert into manual_reviews (
              item_id, review_status, owner_name, priority, downstream, note, reviewed_by
            )
            values (?, ?, ?, ?, ?, ?, 'daily_control')
            """,
            (item_id, review_status, owner_name, priority, downstream, note),
        )

    conn.commit()
    return {"status": "updated", "item_id": item_id}


def save_quality_feedback(
    conn: sqlite3.Connection, feedback_date: str, payload: dict[str, Any]
) -> dict[str, Any]:
    feedback_type = clean_choice(payload.get("feedback_type"), FEEDBACK_TYPES, "")
    if not feedback_type:
        return {"status": "blocked", "error_code": "invalid_feedback_type"}
    conn.execute(
        """
        insert into quality_feedback (
          feedback_date, item_id, feedback_type, note, from_type, to_type, from_risk, to_risk
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feedback_date,
            payload.get("item_id"),
            feedback_type,
            clean_text(payload.get("note")),
            clean_text(payload.get("from_type")),
            clean_text(payload.get("to_type")),
            clean_text(payload.get("from_risk")),
            clean_text(payload.get("to_risk")),
        ),
    )
    conn.commit()
    return {"status": "saved", "feedback_type": feedback_type}


def generate_settlement_draft(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    confirmed_items = [
        item
        for item in load_daily_candidate_summaries(conn, control_date)
        if item["status"] == "confirmed"
    ]
    export_dir = resolve_path(config.root, config.export.directory) / "daily_control_drafts"
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{control_date} 待沉淀草稿.md"
    lines = [
        f"# {control_date} 待沉淀草稿",
        "",
        "> 本文件是本地待沉淀草稿，不写正式日报、正式待办池、Obsidian 正式区或外部系统。",
        "",
        "## 已确认事项",
        "",
    ]
    if not confirmed_items:
        lines.extend(["暂无", ""])
    else:
        for item in confirmed_items:
            lines.extend(
                [
                    f"- {item['item_code']}｜{party_name(item)}｜{item['title']}",
                    f"  - 类型：{item['item_type']}",
                    f"  - 摘要：{item['summary']}",
                    f"  - 负责人：{item['owner_name'] or '未填写'}",
                    f"  - 下游：{item['downstream'] or item['suggested_downstream']}",
                    f"  - 风险：{item['risk_level']}",
                    "",
                ]
            )
    file_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    item_ids = [int(item["id"]) for item in confirmed_items]
    summary = {"confirmed_count": len(confirmed_items), "formal_write_enabled": False}
    conn.execute(
        """
        insert into settlement_drafts (draft_date, file_path, item_ids_json, summary_json)
        values (?, ?, ?, ?)
        """,
        (
            control_date,
            str(file_path),
            json.dumps(item_ids, ensure_ascii=False),
            json.dumps(summary, ensure_ascii=False),
        ),
    )
    conn.commit()
    return SettlementDraftResult("generated", str(file_path), item_ids).__dict__


def load_daily_candidate_summaries(
    conn: sqlite3.Connection, control_date: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select ci.id, ci.item_code, ci.item_type, ci.status, ci.risk_level,
               ci.risk_tags_json, ci.customer_name, ci.channel_name, ci.module_name,
               ci.title, ci.summary, ci.suggested_downstream, ci.first_seen_at,
               ci.last_seen_at,
               (
                 select mr.owner_name from manual_reviews mr
                 where mr.item_id = ci.id
                 order by mr.reviewed_at desc, mr.id desc
                 limit 1
               ) as owner_name,
               (
                 select mr.priority from manual_reviews mr
                 where mr.item_id = ci.id
                 order by mr.reviewed_at desc, mr.id desc
                 limit 1
               ) as priority,
               (
                 select mr.downstream from manual_reviews mr
                 where mr.item_id = ci.id
                 order by mr.reviewed_at desc, mr.id desc
                 limit 1
               ) as downstream
        from candidate_items ci
        where date(ci.first_seen_at) = date(?)
        order by ci.first_seen_at, ci.id
        """,
        (control_date,),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["risk_tags"] = parse_json_list(item.pop("risk_tags_json", "[]"))
        item["owner_name"] = item.get("owner_name") or ""
        item["priority"] = item.get("priority") or "P2"
        item["downstream"] = item.get("downstream") or ""
        item["actions"] = ["confirm", "reject", "change_type", "mark_risk", "assign_owner"]
        items.append(item)
    return items


def latest_run_for_date(conn: sqlite3.Connection, control_date: str) -> dict[str, Any]:
    row = conn.execute(
        """
        select *
        from collection_runs
        where date(coalesce(finished_at, started_at)) = date(?)
        order by id desc
        limit 1
        """,
        (control_date,),
    ).fetchone()
    return dict(row) if row else {}


def quality_feedback_counts(conn: sqlite3.Connection, control_date: str) -> dict[str, int]:
    counts = {key: 0 for key in FEEDBACK_TYPES}
    rows = conn.execute(
        """
        select feedback_type, count(*) as count
        from quality_feedback
        where date(feedback_date) = date(?)
        group by feedback_type
        """,
        (control_date,),
    ).fetchall()
    for row in rows:
        if row["feedback_type"] in counts:
            counts[row["feedback_type"]] = int(row["count"])
    return counts


def latest_draft_for_date(conn: sqlite3.Connection, control_date: str) -> dict[str, Any]:
    row = conn.execute(
        """
        select *
        from settlement_drafts
        where date(draft_date) = date(?)
        order by generated_at desc, id desc
        limit 1
        """,
        (control_date,),
    ).fetchone()
    return dict(row) if row else {}


def build_settlement_check(
    confirmed_items: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
    draft: dict[str, Any],
) -> dict[str, Any]:
    owner_filled = bool(confirmed_items) and all(item["owner_name"] for item in confirmed_items)
    downstream_confirmed = bool(confirmed_items) and all(
        item["downstream"] or item["suggested_downstream"] for item in confirmed_items
    )
    return {
        "confirmed_count": len(confirmed_items),
        "risk_reviewed": not risk_items,
        "owner_filled": owner_filled,
        "downstream_confirmed": downstream_confirmed,
        "draft_generated": bool(draft),
        "draft_path": draft.get("file_path", ""),
        "formal_write_enabled": False,
        "formal_write_reason": "formal_path_not_configured",
        "can_generate_draft": bool(confirmed_items),
    }


def collection_card(run: dict[str, Any]) -> dict[str, Any]:
    if not run:
        return {"key": "collection", "title": "采集状态", "status": "未运行", "count": 0, "error_code": ""}
    return {
        "key": "collection",
        "title": "采集状态",
        "status": run.get("status", "failed"),
        "count": int(run.get("raw_messages_inserted") or 0),
        "error_code": run.get("error_code") or "",
        "sessions_total": int(run.get("sessions_total") or 0),
        "sessions_success": int(run.get("sessions_success") or 0),
        "sessions_failed": int(run.get("sessions_failed") or 0),
    }


def review_card(pending_items: list[dict[str, Any]], risk_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "key": "review",
        "title": "候选审阅",
        "status": "pending" if pending_items else "ok",
        "count": len(pending_items),
        "high_risk_count": len([item for item in risk_items if item["risk_level"] == "high"]),
    }


def settlement_card(
    confirmed_items: list[dict[str, Any]], settlement_check: dict[str, Any]
) -> dict[str, Any]:
    return {
        "key": "settlement",
        "title": "待沉淀",
        "status": "ready" if confirmed_items else "empty",
        "count": len(confirmed_items),
        "draft_generated": settlement_check["draft_generated"],
    }


def quality_card(counts: dict[str, int]) -> dict[str, Any]:
    total = sum(counts.values())
    return {"key": "quality", "title": "规则反馈", "status": "has_feedback" if total else "empty", "count": total}


def build_timeline(
    latest_run: dict[str, Any],
    candidates: list[dict[str, Any]],
    feedback_counts: dict[str, int],
    draft: dict[str, Any],
) -> list[dict[str, Any]]:
    events = []
    if latest_run:
        events.append(
            {
                "key": "collection",
                "label": "今日采集",
                "status": latest_run.get("status", "failed"),
                "error_code": latest_run.get("error_code") or "",
                "count": int(latest_run.get("raw_messages_inserted") or 0),
                "at": latest_run.get("finished_at") or latest_run.get("started_at") or "",
            }
        )
    else:
        events.append({"key": "collection", "label": "今日采集", "status": "未运行", "error_code": "", "count": 0, "at": ""})
    events.append({"key": "review", "label": "候选审阅", "status": "pending", "error_code": "", "count": len([item for item in candidates if item["status"] == "pending"]), "at": ""})
    events.append({"key": "draft", "label": "待沉淀草稿", "status": "generated" if draft else "pending", "error_code": "", "count": 1 if draft else 0, "at": draft.get("generated_at", "") if draft else ""})
    events.append({"key": "quality", "label": "规则反馈", "status": "recorded" if sum(feedback_counts.values()) else "empty", "error_code": "", "count": sum(feedback_counts.values()), "at": ""})
    return events


def parse_json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def clean_choice(value: Any, choices: tuple[str, ...], default: str) -> str:
    text = clean_text(value)
    return text if text in choices else default


def party_name(item: dict[str, Any]) -> str:
    return str(item.get("customer_name") or item.get("channel_name") or "未标对象")
