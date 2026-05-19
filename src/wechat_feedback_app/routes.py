from __future__ import annotations

import hashlib
import sqlite3
import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .collector import collect_messages, latest_run
from .config import AppConfig, PersonConfig, RiskConfig, SessionConfig
from .db import setup_database
from .daily_control import (
    apply_daily_control_action,
    daily_control_summary,
    generate_settlement_draft,
    latest_draft_for_date,
    load_daily_candidate_summaries,
    save_quality_feedback,
)
from .exporter import (
    DEFAULT_TEMPLATE_IDS,
    TEMPLATE_DEFINITIONS,
    export_all_markdown_templates,
    export_feedback_report,
    export_followup_list,
    export_markdown_template,
    load_evidence,
    load_items_for_date,
    load_template_items,
    load_reviews,
    preview_markdown_template,
    redact_visible_text,
)
from .wx_cli_adapter import test_connection, wx_cli_readiness


def create_app(config: AppConfig):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover - exercised by runtime only.
        raise RuntimeError(
            "FastAPI 未安装。请先按 pyproject.toml 安装依赖后再启动后台。"
        ) from exc

    app = FastAPI(title="微信反馈采集工作台")
    conn = setup_database(config)

    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        from fastapi.responses import FileResponse

        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    def status():
        return {
            **safe_status_payload(config),
            "latest_run": latest_run(conn),
            "connection": test_connection(config),
            "wx_cli_ready": wx_cli_readiness(config),
        }

    @app.get("/api/inbox/v1")
    def inbox_v1(control_date: Optional[str] = None):
        return inbox_v1_payload(config, conn, control_date or date.today().isoformat())

    @app.get("/api/daily-center")
    def daily_center(control_date: Optional[str] = None):
        return daily_center_payload(config, conn, control_date or date.today().isoformat())

    @app.get("/api/daily-center/settlements")
    def daily_center_settlements():
        return daily_settlement_center_payload(config, conn)

    @app.get("/api/candidates/resolution-statuses")
    def candidate_resolution_statuses(control_date: Optional[str] = None):
        return candidate_resolution_status_payload(
            config, conn, control_date or date.today().isoformat()
        )

    @app.get("/api/monitor-groups")
    def monitor_groups():
        return monitor_groups_payload(config)

    @app.post("/api/monitor-groups")
    def monitor_group_create(payload: dict[str, Any]):
        return save_monitor_group_payload(config, payload)

    @app.get("/api/monitor-groups/{group_id}")
    def monitor_group_detail(group_id: str):
        payload = monitor_group_detail_payload(config, group_id)
        if payload["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return payload

    @app.put("/api/monitor-groups/{group_id}")
    def monitor_group_update(group_id: str, payload: dict[str, Any]):
        result = save_monitor_group_payload(config, payload, group_id=group_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/monitor-groups/{group_id}/disable")
    def monitor_group_disable(group_id: str):
        result = disable_monitor_group_payload(config, group_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/collect")
    def collect():
        return collect_messages(config, conn).__dict__

    @app.get("/api/items")
    def items(status: Optional[str] = None, export_date: Optional[str] = None):
        selected_date = export_date or date.today().isoformat()
        rows = load_items_for_date(conn, selected_date, include_rejected=True)
        if status:
            rows = [item for item in rows if item["status"] == status]
        return {"items": rows}

    @app.get("/api/items/{item_id}")
    def item_detail(item_id: int):
        row = conn.execute("select * from candidate_items where id = ?", (item_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="candidate item not found")
        item = dict(row)
        item["evidence"] = load_evidence(conn, item_id)
        item["reviews"] = load_reviews(conn, item_id)
        return item

    @app.post("/api/items/{item_id}/review")
    def review(item_id: int, payload: dict[str, Any]):
        row = conn.execute("select id from candidate_items where id = ?", (item_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="candidate item not found")
        review_status = payload.get("review_status", "pending")
        if review_status not in {"pending", "confirmed", "rejected"}:
            raise HTTPException(status_code=400, detail="invalid review_status")
        priority = payload.get("priority", "P2")
        if priority not in {"P0", "P1", "P2", "P3"}:
            raise HTTPException(status_code=400, detail="invalid priority")
        downstream = payload.get("downstream", "none")
        if downstream not in {"product", "tech", "ops", "none"}:
            raise HTTPException(status_code=400, detail="invalid downstream")
        save_review(conn, item_id, review_status, payload, priority, downstream)
        return item_detail(item_id)

    @app.post("/api/export/report")
    def export_report(payload: Optional[dict[str, str]] = None):
        export_date = (payload or {}).get("export_date") or date.today().isoformat()
        return export_feedback_report(config, conn, export_date).__dict__

    @app.post("/api/export/followups")
    def export_followups(payload: Optional[dict[str, str]] = None):
        export_date = (payload or {}).get("export_date") or date.today().isoformat()
        return export_followup_list(config, conn, export_date).__dict__

    @app.get("/api/export/templates")
    def export_templates():
        return export_templates_payload(config, conn, date.today().isoformat())

    @app.post("/api/export/templates/preview")
    def export_template_preview(payload: Optional[dict[str, Any]] = None):
        try:
            return export_template_preview_payload(config, conn, payload or {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/export/templates")
    def export_templates_selected(payload: Optional[dict[str, Any]] = None):
        body = payload or {}
        export_date = str(body.get("export_date") or date.today().isoformat())
        include_pending = parse_bool(body.get("include_pending"), True)
        confirmed_only = parse_bool(body.get("confirmed_only"), False)
        separate_risks = parse_bool(body.get("separate_risks"), True)
        data_source = resolve_export_data_source(
            config,
            conn,
            export_date,
            body.get("data_source"),
            include_pending=include_pending,
            confirmed_only=confirmed_only,
        )
        source_items = real_trial_template_items(config) if data_source == "real_trial" else None
        data_source = "real_trial" if source_items is not None else "workspace"
        template_ids = body.get("template_ids")
        if parse_bool(body.get("export_all"), False):
            selected_template_ids = DEFAULT_TEMPLATE_IDS
        elif isinstance(template_ids, list) and template_ids:
            selected_template_ids = [str(item) for item in template_ids]
        else:
            selected_template_ids = [str(body.get("template_id") or "daily_review")]

        try:
            if len(selected_template_ids) == 1:
                result = export_markdown_template(
                    config,
                    conn,
                    export_date,
                    selected_template_ids[0],
                    include_pending=include_pending,
                    confirmed_only=confirmed_only,
                    separate_risks=separate_risks,
                    source_items=source_items,
                )
                return {
                    "status": "ok",
                    "export_date": export_date,
                    "data_source": data_source,
                    "results": [result.__dict__],
                    "formal_write_enabled": False,
                    "message": "已导出本地 Markdown，不写正式待办池 / 正式日报。",
                }
            return export_all_markdown_templates(
                config,
                conn,
                export_date,
                include_pending=include_pending,
                confirmed_only=confirmed_only,
                separate_risks=separate_risks,
                template_ids=selected_template_ids,
                source_items=source_items,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/config")
    def get_config():
        return safe_config_payload(config)

    @app.get("/api/wx-cli/test")
    def wx_cli_test():
        return test_connection(config)

    @app.get("/api/wx-cli/readiness")
    def wx_cli_ready():
        return wx_cli_readiness(config)

    @app.get("/api/real-trial/latest")
    def real_trial_latest():
        return latest_real_trial_payload(config)

    @app.get("/api/real-trial/latest/items")
    def real_trial_latest_items():
        return real_trial_latest_items_payload(config)

    @app.get("/api/real-trial/latest/messages")
    def real_trial_latest_messages():
        return real_trial_latest_messages_payload(config)

    @app.get("/api/real-trial/latest/items/{item_id}/messages")
    def real_trial_candidate_messages(item_id: int):
        return real_trial_candidate_messages_payload(config, item_id)

    @app.post("/api/real-trial/latest/import")
    def real_trial_import():
        return import_latest_real_trial_candidates(config, conn)

    @app.post("/api/real-trial/sender-map")
    def real_trial_sender_map(payload: dict[str, Any]):
        return save_sender_mapping_payload(conn, payload)

    @app.get("/api/config-center")
    def config_center():
        return config_center_payload(config)

    @app.post("/api/config-center")
    def save_config_center(payload: dict[str, Any]):
        return save_config_center_payload(config, payload)

    @app.post("/api/real-trial/run")
    def real_trial_run(payload: dict[str, Any]):
        return real_trial_run_plan(config, payload)

    @app.get("/api/daily-control")
    def daily_control(control_date: Optional[str] = None):
        return daily_control_payload(config, conn, control_date or date.today().isoformat())

    @app.post("/api/daily-control/items/{item_id}")
    def daily_control_item_action(item_id: int, payload: dict[str, Any]):
        result = apply_daily_control_action(conn, item_id, payload)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="candidate item not found")
        return result

    @app.post("/api/daily-control/feedback")
    def daily_control_feedback(payload: dict[str, Any]):
        feedback_date = str(payload.get("feedback_date") or date.today().isoformat())
        return save_quality_feedback(conn, feedback_date, payload)

    @app.post("/api/daily-control/draft")
    def daily_control_draft(payload: Optional[dict[str, Any]] = None):
        control_date = str((payload or {}).get("control_date") or date.today().isoformat())
        return generate_settlement_draft(config, conn, control_date)

    @app.get("/api/daily-control/draft-preview")
    def daily_control_draft_preview(
        control_date: Optional[str] = None, data_source: Optional[str] = None
    ):
        body: dict[str, Any] = {"control_date": control_date or date.today().isoformat()}
        if data_source is not None:
            body["data_source"] = data_source
        return draft_report_preview_payload(config, conn, body)

    @app.post("/api/daily-control/draft-preview")
    def daily_control_draft_preview_regenerate(payload: Optional[dict[str, Any]] = None):
        body = payload or {}
        return regenerate_draft_report_payload(config, conn, body)

    @app.post("/api/daily-control/formal-write")
    def daily_control_formal_write():
        return {
            "status": "blocked",
            "error_code": "formal_path_not_configured",
            "formal_write_enabled": False,
            "message": "正式区路径未配置；当前只允许生成本地待沉淀草稿。",
        }

    return app


def parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def export_templates_payload(
    config: AppConfig, conn: sqlite3.Connection, export_date: str
) -> dict[str, Any]:
    data_source = resolve_export_data_source(
        config,
        conn,
        export_date,
        None,
        include_pending=True,
        confirmed_only=False,
    )
    source_items = real_trial_template_items(config) if data_source == "real_trial" else None
    items = load_template_items(
        conn,
        export_date,
        include_pending=True,
        confirmed_only=False,
        source_items=source_items,
    )
    risk_count = len([item for item in items if item["risk_level"] != "none"])
    pending_count = len([item for item in items if item["status"] == "pending"])
    return {
        "status": "ok",
        "export_date": export_date,
        "templates": [
            {
                "template_id": template_id,
                "template_name": str(definition["name"]),
                "filename": f"{export_date} {definition['filename_suffix']}",
            }
            for template_id, definition in TEMPLATE_DEFINITIONS.items()
        ],
        "summary": {
            "candidate_count": len(items),
            "pending_count": pending_count,
            "risk_count": risk_count,
            "mode": config.wx_cli.mode,
            "default_real_read_enabled": config.wx_cli.real_read_enabled,
        },
        "data_source": data_source,
        "data_source_label": data_source_label(data_source),
        "human_task": transfer_task_payload("product_tech_summary", data_source, items),
        "safety_boundary": "本地 Markdown，不写正式待办池 / 正式日报 / Obsidian 正式区或外部系统。",
        "formal_write_enabled": False,
    }


def daily_control_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    payload = daily_control_summary(config, conn, control_date)
    real_trial = latest_real_trial_payload(config)
    real_trial_items = real_trial_latest_items_payload(config)
    real_trial_count = int(real_trial_items.get("count") or 0)
    main_candidate_count = int(payload.get("top_status", {}).get("candidate_count") or 0)
    notice_visible = main_candidate_count == 0 and real_trial_count > 0
    payload["real_trial"] = real_trial
    payload["real_trial_items"] = {
        "status": real_trial_items.get("status", "not_found"),
        "source_label": real_trial_items.get("source_label", ""),
        "count": real_trial_count,
        "items": real_trial_items.get("items", []),
    }
    payload["real_trial_notice"] = {
        "visible": notice_visible,
        "message": (
            "当前主工作台无待确认事项；最近真实试读有候选，尚未合并进主工作台。"
            if notice_visible
            else ""
        ),
    }
    payload["real_trial_actions"] = (
        [
            {
                "action": "import_to_workspace",
                "label": "加入待确认",
                "message": "只写本地候选，不写正式待办池、正式日报或外部系统。",
            },
            {
                "action": "export_templates_from_trial",
                "label": "用最近真实试读生成转述摘要",
                "message": "只写本地 Markdown，不写正式区或外部系统。",
            },
        ]
        if notice_visible
        else []
    )
    return payload


def inbox_v1_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    daily = daily_control_payload(config, conn, control_date)
    candidate_inbox = candidate_inbox_payload(config, conn, control_date)
    candidate_source = str(candidate_inbox.get("source_key") or "workspace")
    candidate_raw_items = list(candidate_inbox.get("raw_items") or [])
    candidate_inbox = {
        key: value
        for key, value in candidate_inbox.items()
        if key not in {"source_key", "raw_items"}
    }
    real_trial = daily.get("real_trial", {})
    real_trial_items = daily.get("real_trial_items", {})
    top = daily.get("top_status", {})
    draft = latest_draft_for_date(conn, control_date)
    selected_session = first_enabled_whitelist_session(config)
    raw_count = int(real_trial.get("raw_count") or 0)
    candidate_count = int(real_trial.get("candidate_count") or 0)
    risk_count = int(real_trial.get("risk_count") or 0)
    workspace_candidate_count = int(top.get("candidate_count") or 0)
    pending_count = int(top.get("pending_count") or 0)
    trial_draft_available = workspace_candidate_count == 0 and candidate_count > 0
    suggested_draft_source = "real_trial" if trial_draft_available else "workspace"
    return {
        "status": "ok",
        "title": "微信反馈防漏收件箱 V1",
        "control_date": control_date,
        "top_status": {
            "mode": config.wx_cli.mode,
            "trial_source": real_trial.get("source_label") or "real_trial",
            "trial_finished_at": real_trial.get("trial_finished_at") or "",
            "raw_count": raw_count,
            "candidate_count": candidate_count,
            "risk_count": risk_count,
            "workspace_candidate_count": workspace_candidate_count,
            "pending_count": pending_count,
            "draft_status": "机器初稿 / 待审阅" if draft else "未生成",
            "collection_status": top.get("collection_status") or "未运行",
            "error_code": top.get("error_code") or "",
        },
        "human_status": human_status_payload(
            config=config,
            top=top,
            real_trial=real_trial,
            raw_count=raw_count,
            candidate_count=candidate_count,
            risk_count=risk_count,
            pending_count=pending_count,
            draft=draft,
        ),
        "message_vs_candidate_explain": (
            "50 条是原始消息，3 条是抽出来的候选事项；原始消息不等于候选事项，"
            "候选仍需人工确认后才能沉淀。"
        ),
        "workflow_steps": [
            {"key": "trial_read", "label": "试读 50 条", "status": human_count_status(raw_count)},
            {"key": "message_review", "label": "消息明细", "status": human_count_status(raw_count)},
            {"key": "sender_identity", "label": "发送人识别", "status": "本地审阅"},
            {"key": "candidate_items", "label": "候选事项", "status": human_count_status(candidate_count)},
            {"key": "group_customer_tags", "label": "群 / 客户打标", "status": group_profile_status(selected_session)},
            {"key": "manual_confirm", "label": "人工确认", "status": "待处理"},
            {"key": "draft_report", "label": "草稿日报", "status": "已生成" if draft else "未生成"},
            {"key": "transfer_summary", "label": "转述摘要", "status": "本地生成"},
        ],
        "group_profile": group_profile_payload(selected_session),
        "real_trial": {
            "status": real_trial.get("status", "not_found"),
            "raw_count": raw_count,
            "candidate_count": candidate_count,
            "risk_count": risk_count,
            "items_count": int(real_trial_items.get("count") or 0),
            "fixture_service_notice": bool(real_trial.get("fixture_service_notice")),
        },
        "trial_draft_prompt": {
            "visible": trial_draft_available,
            "message": (
                f"发现最近试读 {candidate_count} 条候选；当前今日处理区为空，可先生成试读草稿。"
                if trial_draft_available
                else ""
            ),
            "primary_action": "generate_trial_draft",
            "primary_action_label": "生成试读草稿",
        },
        "candidate_inbox": candidate_inbox,
        "transfer_task": transfer_task_payload(
            "product_tech_summary",
            candidate_source,
            candidate_raw_items,
        ),
        "suggested_draft_data_source": suggested_draft_source,
        "actions": [
            {
                "action": "view_messages",
                "target": "realTrialMessagesPanel",
                "label": "查看最近 50 条消息明细",
            },
            {
                "action": "import_to_workspace",
                "target": "importRealTrialBtn",
                "label": "进入候选收件箱处理",
            },
            {
                "action": "open_draft",
                "target": "draftReportPanel",
                "label": "查看草稿日报 / 机器初稿",
            },
            {
                "action": "export_templates",
                "target": "exportTemplateBtn",
                "label": "查看转述摘要",
            },
        ],
        "safety": {
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "formal_write_enabled": False,
            "local_review_only": True,
            "no_external_send": True,
            "no_auto_reply": True,
        },
    }


def daily_center_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    candidates = [
        item
        for item in load_daily_candidate_summaries(conn, control_date)
        if clean_text(item.get("status")) != "rejected"
    ]
    historical_items = historical_unfollowed_items(conn, control_date)
    latest_draft = latest_draft_for_date(conn, control_date)
    report_body = render_daily_center_report(control_date, candidates, historical_items)
    has_report = bool(report_body.strip())
    has_draft = bool(latest_draft)
    monitor_count = daily_center_monitor_group_count(config)
    new_issue_count = len(candidates)
    historical_count = len(historical_items)
    report_status_label = "已生成" if has_report else "未生成"
    settlement_status_label = (
        "已沉淀" if has_draft else ("待沉淀" if has_report else "暂无可沉淀")
    )
    return {
        "status": "ok",
        "page_title": "日报中心",
        "control_date": control_date,
        "summary": {
            "report_status_label": report_status_label,
            "settlement_status_label": settlement_status_label,
            "monitor_group_count": monitor_count,
            "new_issue_count": new_issue_count,
            "historical_unfollowed_count": historical_count,
        },
        "cards": [
            {
                "label": "日报状态",
                "value": report_status_label,
                "count": 1 if has_report else 0,
            },
            {
                "label": "沉淀状态",
                "value": settlement_status_label,
                "count": 1 if has_draft else 0,
            },
            {"label": "监控群数", "value": f"{monitor_count} 个", "count": monitor_count},
            {"label": "新发现问题", "value": f"{new_issue_count} 条", "count": new_issue_count},
            {
                "label": "历史未跟进",
                "value": f"{historical_count} 条",
                "count": historical_count,
            },
        ],
        "report": {
            "title": f"{control_date} 微信反馈日报",
            "status_label": report_status_label,
            "settlement_status_label": settlement_status_label,
            "body_markdown": report_body,
            "empty_state_label": (
                "" if has_report else "当前还没有可展示日报；可先生成本地机器初稿。"
            ),
            "body_source_label": "本地候选生成",
        },
        "actions": daily_center_actions(has_report, has_draft),
        "settlement_center": daily_settlement_center_payload(config, conn),
        "candidate_destinations": candidate_resolution_status_payload(
            config, conn, control_date
        ),
        "safety": {
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "formal_write_enabled": False,
            "save_triggers_collection": False,
            "local_only": True,
            "no_external_send": True,
        },
    }


def daily_settlement_center_payload(
    config: AppConfig, conn: sqlite3.Connection
) -> dict[str, Any]:
    rows = []
    for control_date in daily_center_dates(conn):
        candidates = [
            item
            for item in load_daily_candidate_summaries(conn, control_date)
            if clean_text(item.get("status")) != "rejected"
        ]
        historical_count = len(historical_unfollowed_items(conn, control_date))
        draft = latest_draft_for_date(conn, control_date)
        has_report = bool(candidates or historical_count or draft)
        rows.append(
            {
                "date": control_date,
                "monitor_group_count": daily_center_monitor_group_count(config),
                "new_issue_count": len(candidates),
                "historical_unfollowed_count": historical_count,
                "report_status_label": "已生成" if has_report else "未生成",
                "settlement_status_label": (
                    "已沉淀" if draft else ("待沉淀" if has_report else "暂无可沉淀")
                ),
                "actions": [
                    {
                        "action": "open_daily_report",
                        "label": "查看日报",
                        "enabled": has_report,
                    },
                    {
                        "action": "confirm_settlement",
                        "label": "确认沉淀",
                        "enabled": False,
                    },
                ],
            }
        )
    return {
        "status": "ok",
        "title": "日报沉淀中心",
        "count": len(rows),
        "items": rows,
        "safety": {
            "formal_write_enabled": False,
            "save_triggers_collection": False,
        },
    }


def daily_center_dates(conn: sqlite3.Connection) -> list[str]:
    dates: set[str] = set()
    rows = conn.execute(
        """
        select date(first_seen_at) as item_date
        from candidate_items
        where first_seen_at is not null
        union
        select date(draft_date) as item_date
        from settlement_drafts
        where draft_date is not null
        union
        select date(coalesce(finished_at, started_at)) as item_date
        from collection_runs
        where coalesce(finished_at, started_at) is not null
        """
    ).fetchall()
    for row in rows:
        item_date = clean_text(row["item_date"])
        if item_date:
            dates.add(item_date)
    if not dates:
        dates.add(date.today().isoformat())
    return sorted(dates, reverse=True)


def historical_unfollowed_items(
    conn: sqlite3.Connection, control_date: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, item_code, item_type, status, risk_level, risk_tags_json,
               customer_name, channel_name, module_name, title, summary,
               suggested_downstream, first_seen_at, last_seen_at
        from candidate_items
        where date(first_seen_at) < date(?)
          and status in ('pending', 'confirmed')
        order by first_seen_at, id
        """,
        (control_date,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["risk_tags"] = parse_json_list(item.pop("risk_tags_json", "[]"))
        items.append(item)
    return items


def render_daily_center_report(
    control_date: str,
    new_items: list[dict[str, Any]],
    historical_items: list[dict[str, Any]],
) -> str:
    if not new_items and not historical_items:
        return ""
    lines = [
        f"# {control_date} 微信反馈日报",
        "",
        "## 一、昨日总览",
        f"- 新发现问题：{len(new_items)} 条",
        f"- 历史未跟进：{len(historical_items)} 条",
        "",
        "## 二、重点跟进",
    ]
    if new_items:
        for item in new_items[:10]:
            lines.append(
                f"- {redact_visible_text(item.get('item_code'))}｜"
                f"{item_type_label(item.get('item_type'))}｜"
                f"{redact_visible_text(item.get('summary') or item.get('title'))}"
            )
    else:
        lines.append("- 暂无新发现问题")
    lines.extend(["", "## 三、历史未跟进"])
    if historical_items:
        for item in historical_items[:10]:
            lines.append(
                f"- {redact_visible_text(item.get('item_code'))}｜"
                f"{candidate_home_status_label(item, set())}｜"
                f"{redact_visible_text(item.get('summary') or item.get('title'))}"
            )
    else:
        lines.append("- 暂无历史未跟进")
    lines.extend(
        [
            "",
            "## 四、今日建议",
            "- 先确认新发现问题，再决定是否生成本地待沉淀草稿。",
            "- 正式沉淀仍需人工确认，本地后台不会自动外发或写正式区。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def daily_center_actions(has_report: bool, has_draft: bool) -> dict[str, dict[str, Any]]:
    return {
        "refresh_report": {
            "label": "生成/刷新日报",
            "enabled": True,
            "hint": "只生成本地日报内容，不触发真实读取。",
        },
        "copy_full_text": {
            "label": "复制全文",
            "enabled": has_report,
            "hint": "复制当前本地日报内容。",
        },
        "export_markdown": {
            "label": "导出 Markdown",
            "enabled": has_report,
            "hint": "只导出本地文件。",
        },
        "confirm_settlement": {
            "label": "确认沉淀",
            "enabled": False,
            "hint": "正式沉淀仍需人工确认，本棒只提供本地状态口径。",
        },
        "mark_recheck": {
            "label": "标记需要重看",
            "enabled": has_report or has_draft,
            "hint": "用于后续人工复核。",
        },
    }


def candidate_resolution_status_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    del config
    drafted_ids = latest_draft_item_ids(conn, control_date)
    items = load_daily_candidate_summaries(conn, control_date)
    rows = []
    counts = {status["label"]: 0 for status in candidate_home_status_options()}
    for item in items:
        label = candidate_home_status_label(item, drafted_ids)
        counts[label] = counts.get(label, 0) + 1
        rows.append(
            {
                "item_id": int(item.get("id") or 0),
                "display_id": redact_visible_text(item.get("item_code")),
                "home_status_label": label,
                "action_label": candidate_home_action_label(label),
                "summary_safe": redact_visible_text(
                    item.get("summary") or item.get("title") or ""
                ),
            }
        )
    return {
        "status": "ok",
        "control_date": control_date,
        "available_statuses": candidate_home_status_options(),
        "counts": counts,
        "items": rows,
        "safety": {
            "formal_write_enabled": False,
            "raw_evidence_returned": False,
        },
    }


def candidate_home_status_options() -> list[dict[str, str]]:
    return [
        {"value": "pending_confirm", "label": "待确认"},
        {"value": "confirmed_followup", "label": "已确认跟进"},
        {"value": "ignored", "label": "已忽略"},
        {"value": "written_to_daily", "label": "已写入日报"},
        {"value": "closed", "label": "已收口"},
    ]


def candidate_home_status_label(
    item: dict[str, Any], drafted_ids: set[int]
) -> str:
    item_id = int(item.get("id") or 0)
    status = clean_text(item.get("status")) or "pending"
    if item_id in drafted_ids:
        return "已写入日报"
    if status == "confirmed":
        return "已确认跟进"
    if status == "rejected":
        return "已忽略"
    return "待确认"


def candidate_home_action_label(label: str) -> str:
    return {
        "待确认": "去确认",
        "已确认跟进": "继续跟进",
        "已忽略": "查看原因",
        "已写入日报": "查看日报",
        "已收口": "查看记录",
    }.get(label, "查看")


def human_status_payload(
    *,
    config: AppConfig,
    top: dict[str, Any],
    real_trial: dict[str, Any],
    raw_count: int,
    candidate_count: int,
    risk_count: int,
    pending_count: int,
    draft: dict[str, Any] | None,
) -> dict[str, Any]:
    latest_finished = clean_text(real_trial.get("trial_finished_at")) or "未产生"
    collection_status = clean_text(top.get("collection_status")) or "未运行"
    error_code = clean_text(top.get("error_code"))
    cards = [
        {
            "key": "service_health",
            "label": "服务健康",
            "value": "本地服务可用",
            "hint": "页面和本地数据库可访问；技术诊断默认折叠。",
        },
        {
            "key": "real_reading",
            "label": "真实读取",
            "value": "默认关闭" if not config.wx_cli.real_read_enabled else "临时开启",
            "hint": "不会自动抓取；需要人工确认后才试读。",
        },
        {
            "key": "latest_result",
            "label": "最近一次可用结果",
            "value": f"{raw_count} 条原始消息 / {candidate_count} 条候选",
            "hint": f"上次成功试读：{latest_finished}",
        },
        {
            "key": "candidate_items",
            "label": "候选事项",
            "value": f"待确认 {pending_count} 条",
            "hint": f"风险候选 {risk_count} 条；候选需要人工判断。",
        },
        {
            "key": "draft_report",
            "label": "草稿日报",
            "value": "机器初稿待审阅" if draft else "未生成",
            "hint": "只生成本地草稿，不写正式区。",
        },
        {
            "key": "daily_closeout",
            "label": "今日收口",
            "value": human_collection_status(collection_status),
            "hint": f"本次失败原因：{error_code}" if error_code else "暂无失败原因；下一步按候选确认流处理。",
        },
    ]
    return {
        "cards": cards,
        "auto_fetch": {
            "enabled": False,
            "label": "自动抓取未开启",
            "frequency": "未配置自动抓取",
            "last_success": latest_finished,
            "next_planned": "未计划",
            "failure_reason": error_code or "",
        },
        "diagnostic_details": {
            "collapsed": True,
            "collection_status": collection_status,
            "error_code": error_code,
            "current_service_mode": config.wx_cli.mode,
            "current_service_is_real": config.wx_cli.mode == "real",
            "trial_artifact_status": clean_text(real_trial.get("status")) or "not_found",
        },
    }


def human_collection_status(status: str) -> str:
    return {
        "success": "已跑通",
        "partial_failed": "部分失败",
        "failed": "失败",
        "未运行": "未运行",
        "not_run": "未运行",
    }.get(status, status or "未运行")


def first_enabled_whitelist_session(config: AppConfig) -> SessionConfig | None:
    return next(
        (session for session in config.sessions if session.enabled and session.is_whitelisted),
        None,
    )


def status_by_count(count: int) -> str:
    return "ready" if count > 0 else "empty"


def human_count_status(count: int) -> str:
    return "可查看" if count > 0 else "暂无"


def group_profile_status(session: SessionConfig | None) -> str:
    if session is None:
        return "未配置"
    required = [
        session.customer_name,
        session.owner_name,
        session.module_name,
        session.customer_stage,
        session.group_type,
    ]
    return "已配置" if all(required) else "待补充"


def group_profile_payload(session: SessionConfig | None) -> dict[str, Any]:
    if session is None:
        return {
            "configured": False,
            "customer_name": "",
            "group_owner": "",
            "module_name": "",
            "customer_stage": "",
            "group_type": "",
            "common_contacts_count": 0,
            "common_contacts": [],
            "reply_notes_configured": False,
        }
    return {
        "configured": True,
        "customer_name": session.customer_name,
        "group_owner": session.owner_name,
        "module_name": session.module_name,
        "customer_stage": session.customer_stage,
        "group_type": session.group_type,
        "common_contacts_count": len(session.common_contacts),
        "common_contacts": list(session.common_contacts),
        "reply_notes_configured": bool(session.reply_notes),
    }


def export_template_preview_payload(
    config: AppConfig, conn: sqlite3.Connection, body: dict[str, Any]
) -> dict[str, object]:
    export_date = str(body.get("export_date") or date.today().isoformat())
    include_pending = parse_bool(body.get("include_pending"), True)
    confirmed_only = parse_bool(body.get("confirmed_only"), False)
    separate_risks = parse_bool(body.get("separate_risks"), True)
    template_id = str(body.get("template_id") or "daily_review")
    data_source = resolve_export_data_source(
        config,
        conn,
        export_date,
        body.get("data_source"),
        include_pending=include_pending,
        confirmed_only=confirmed_only,
    )
    source_items = real_trial_template_items(config) if data_source == "real_trial" else None
    preview_items = load_template_items(
        conn,
        export_date,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
        source_items=source_items,
    )
    result = preview_markdown_template(
        config,
        conn,
        export_date,
        template_id,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
        separate_risks=separate_risks,
        source_items=source_items,
    )
    result["data_source"] = "real_trial" if source_items is not None else "workspace"
    result["data_source_label"] = data_source_label(result["data_source"])
    result["human_task"] = transfer_task_payload(template_id, result["data_source"], preview_items)
    return result


def draft_report_preview_payload(
    config: AppConfig, conn: sqlite3.Connection, body: dict[str, Any]
) -> dict[str, Any]:
    control_date = str(body.get("control_date") or date.today().isoformat())
    data_source = resolve_draft_data_source(config, conn, control_date, body.get("data_source"))
    items = draft_source_items(config, conn, control_date, data_source)
    risk_count = len([item for item in items if item["risk_level"] != "none"])
    latest_draft = latest_draft_for_date(conn, control_date)
    generated_at = str(latest_draft.get("generated_at") or "")
    preview_markdown = render_machine_draft_preview(control_date, data_source, items)
    suggested_from_trial = bool(
        data_source == "real_trial" and clean_text(body.get("data_source")) == ""
    )
    return {
        "status": "ok",
        "draft_status": "机器初稿 / 待审阅",
        "generated_at": generated_at,
        "data_source": data_source,
        "data_source_label": data_source_label(data_source),
        "suggested_from_trial": suggested_from_trial,
        "candidate_count": len(items),
        "item_count": len(items),
        "risk_count": risk_count,
        "formal_write_enabled": False,
        "formal_write_status": "禁用 / 未写入",
        "formal_written": False,
        "local_preview_saved": False,
        "file_path": relative_to_root(config, Path(latest_draft.get("file_path", ""))) if latest_draft.get("file_path") else "",
        "preview_markdown": preview_markdown,
        "items": draft_link_items(items, data_source),
        "next_step": draft_next_step(data_source, len(items), suggested_from_trial),
        "safety_boundary": "本地机器初稿，需人工审阅；不写正式待办池 / 正式日报 / Obsidian 正式区或外部系统。",
    }


def regenerate_draft_report_payload(
    config: AppConfig, conn: sqlite3.Connection, body: dict[str, Any]
) -> dict[str, Any]:
    control_date = str(body.get("control_date") or date.today().isoformat())
    data_source = resolve_draft_data_source(config, conn, control_date, body.get("data_source"))
    items = draft_source_items(config, conn, control_date, data_source)
    preview_markdown = render_machine_draft_preview(control_date, data_source, items)
    file_path = write_machine_draft(config, conn, control_date, data_source, preview_markdown, items)
    payload = draft_report_preview_payload(
        config, conn, {"control_date": control_date, "data_source": data_source}
    )
    payload["local_preview_saved"] = True
    payload["file_path"] = relative_to_root(config, file_path)
    return payload


def safe_status_payload(config: AppConfig) -> dict[str, Any]:
    enabled_whitelist_count = len(
        [
            session
            for session in config.sessions
            if session.enabled and session.is_whitelisted
        ]
    )
    return {
        "mode": config.wx_cli.mode,
        "real_trial": {
            "enabled": config.wx_cli.real_read_enabled,
            "session_configured": bool(config.wx_cli.real_allowed_session.strip()),
            "enabled_whitelist_count": enabled_whitelist_count,
            "lookback_hours": min(max(1, int(config.wx_cli.real_lookback_hours)), 2),
            "limit": min(max(1, int(config.wx_cli.real_limit)), 50),
        },
    }


def safe_config_payload(config: AppConfig) -> dict[str, Any]:
    enabled_sessions = [session for session in config.sessions if session.enabled]
    enabled_whitelist = [
        session for session in enabled_sessions if session.is_whitelisted
    ]
    return {
        "app": {
            "host": config.app.host,
            "port": config.app.port,
        },
        "database": {
            "path_configured": bool(config.database.path.strip()),
        },
        "wx_cli": {
            "mode": config.wx_cli.mode,
            "binary_configured": bool(config.wx_cli.binary.strip()),
            "timeout_seconds": config.wx_cli.timeout_seconds,
            "fixture_dir_configured": bool(config.wx_cli.fixture_dir.strip()),
            "real_read_enabled": config.wx_cli.real_read_enabled,
            "trial_session_configured": bool(
                config.wx_cli.real_allowed_session.strip()
            ),
            "real_lookback_hours": min(
                max(1, int(config.wx_cli.real_lookback_hours)), 2
            ),
            "real_limit": min(max(1, int(config.wx_cli.real_limit)), 50),
        },
        "collector": {
            "interval_minutes": config.collector.interval_minutes,
            "lookback_minutes": config.collector.lookback_minutes,
        },
        "export": {
            "directory_configured": bool(config.export.directory.strip()),
        },
        "session_summary": {
            "total_count": len(config.sessions),
            "enabled_count": len(enabled_sessions),
            "enabled_whitelist_count": len(enabled_whitelist),
        },
        "internal_people": {
            "count": len(config.internal_people),
        },
        "risk": {
            "keyword_count": len(config.risk.keywords),
            "sensitive_keyword_count": len(config.risk.sensitive_keywords),
        },
    }


def latest_real_trial_payload(config: AppConfig) -> dict[str, Any]:
    data_dir = Path(config.root) / "data"
    latest_db = latest_real_trial_db(data_dir)
    base_payload = {
        "status": "not_found",
        "mode": "real",
        "source_label": "",
        "trial_finished_at": "",
        "current_service_mode": config.wx_cli.mode,
        "current_service_is_real": config.wx_cli.mode == "real",
        "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        "fixture_service_notice": config.wx_cli.mode != "real",
        "raw_count": 0,
        "candidate_count": 0,
        "risk_count": 0,
        "candidate_status_counts": {},
        "collection_run": {},
        "sqlite_path": "",
        "sqlite_exists": False,
        "export_directory": "",
        "export_directory_exists": False,
        "read_shape": {
            "limit": 50,
            "since_used": False,
        },
    }
    if latest_db is None:
        return base_payload

    export_dir = real_trial_export_dir(config, latest_db)
    try:
        stats = read_real_trial_stats(latest_db)
    except sqlite3.Error:
        return {
            **base_payload,
            "status": "db_error",
            "source_label": source_label_for_trial(latest_db),
            "sqlite_path": relative_to_root(config, latest_db),
            "sqlite_exists": latest_db.exists(),
            "export_directory": relative_to_root(config, export_dir),
            "export_directory_exists": export_dir.exists(),
        }

    return {
        **base_payload,
        **stats,
        "status": "ok",
        "source_label": source_label_for_trial(latest_db),
        "sqlite_path": relative_to_root(config, latest_db),
        "sqlite_exists": latest_db.exists(),
        "export_directory": relative_to_root(config, export_dir),
        "export_directory_exists": export_dir.exists(),
    }


def real_trial_latest_items_payload(config: AppConfig) -> dict[str, Any]:
    latest_db = latest_real_trial_db(Path(config.root) / "data")
    if latest_db is None:
        return {"status": "not_found", "count": 0, "items": []}
    try:
        uri = f"file:{latest_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                select id, item_code, item_type, status, risk_level, risk_tags_json,
                       module_name, title, summary, suggested_downstream,
                       first_seen_at, last_seen_at,
                       (
                         select count(*)
                         from candidate_item_messages cim
                         where cim.item_id = candidate_items.id
                       ) as source_message_count
                from candidate_items
                order by first_seen_at, id
                """
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {"status": "db_error", "count": 0, "items": []}

    items = []
    for row in rows:
        item = dict(row)
        item["risk_tags"] = parse_json_list(item.pop("risk_tags_json", "[]"))
        item["risk_tags"] = [redact_visible_text(tag) for tag in item["risk_tags"]]
        for field in ["module_name", "title", "summary"]:
            item[field] = redact_visible_text(item.get(field))
        item["human_item_type"] = item_type_label(item.get("item_type"))
        item["source_message_count"] = int(item.get("source_message_count") or 0)
        item["extraction_reason"] = extraction_reason_for_item(item)
        item["detail_actions"] = ["确认", "驳回", "改类型", "补充说明", "撤销"]
        items.append(item)
    return {
        "status": "ok",
        "source_label": source_label_for_trial(latest_db),
        "count": len(items),
        "items": items,
    }


def real_trial_latest_messages_payload(config: AppConfig) -> dict[str, Any]:
    latest_db = latest_real_trial_db(Path(config.root) / "data")
    if latest_db is None:
        return {"status": "not_found", "source_label": "", "count": 0, "messages": [], "senders": []}
    try:
        uri = f"file:{latest_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            messages = real_trial_message_rows(conn)
        finally:
            conn.close()
    except sqlite3.Error:
        return {"status": "db_error", "source_label": source_label_for_trial(latest_db), "count": 0, "messages": [], "senders": []}

    return {
        "status": "ok",
        "source_label": source_label_for_trial(latest_db),
        "count": len(messages),
        "messages": messages,
        "senders": sender_summary(messages),
    }


def real_trial_candidate_messages_payload(
    config: AppConfig, item_id: int
) -> dict[str, Any]:
    latest_db = latest_real_trial_db(Path(config.root) / "data")
    if latest_db is None:
        return {"status": "not_found", "candidate_ref": "", "count": 0, "messages": []}
    try:
        uri = f"file:{latest_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            candidate = conn.execute(
                "select id, item_code from candidate_items where id = ?", (item_id,)
            ).fetchone()
            if candidate is None:
                return {"status": "not_found", "candidate_ref": "", "count": 0, "messages": []}
            messages = real_trial_message_rows(conn, item_id=item_id)
        finally:
            conn.close()
    except sqlite3.Error:
        return {"status": "db_error", "candidate_ref": "", "count": 0, "messages": []}

    return {
        "status": "ok",
        "candidate_ref": str(candidate["item_code"]),
        "count": len(messages),
        "messages": messages,
    }


def import_latest_real_trial_candidates(
    config: AppConfig, conn: sqlite3.Connection
) -> dict[str, Any]:
    payload = real_trial_latest_items_payload(config)
    if payload.get("status") != "ok":
        return {
            "status": payload.get("status", "not_found"),
            "imported_count": 0,
            "duplicated_count": 0,
            "formal_write_enabled": False,
        }

    imported = 0
    duplicated = 0
    source_label = str(payload.get("source_label") or "real_trial")
    for item in payload.get("items", []):
        item_code = clean_trial_item_code(source_label, str(item.get("item_code") or "item"))
        aggregate_key = f"real_trial:{source_label}:{item.get('item_code')}"
        try:
            conn.execute(
                """
                insert into candidate_items (
                  item_code, item_type, status, risk_level, risk_tags_json,
                  customer_name, channel_name, module_name, title, summary,
                  suggested_downstream, aggregate_key, first_seen_at, last_seen_at
                )
                values (?, ?, 'pending', ?, ?, '', '', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_code,
                    safe_item_type(item.get("item_type")),
                    safe_risk_level(item.get("risk_level")),
                    json.dumps(item.get("risk_tags", []), ensure_ascii=False),
                    clean_text(item.get("module_name")),
                    clean_text(item.get("title")),
                    clean_text(item.get("summary")),
                    safe_downstream(item.get("suggested_downstream")),
                    aggregate_key,
                    clean_text(item.get("first_seen_at")) or date.today().isoformat(),
                    clean_text(item.get("last_seen_at")) or date.today().isoformat(),
                ),
            )
            imported += 1
        except sqlite3.IntegrityError:
            duplicated += 1
    conn.commit()
    return {
        "status": "imported",
        "source_label": source_label,
        "imported_count": imported,
        "duplicated_count": duplicated,
        "formal_write_enabled": False,
        "message": "已加入本地待确认候选；不写正式待办池、正式日报或外部系统。",
    }


def save_sender_mapping_payload(
    conn: sqlite3.Connection, payload: dict[str, Any]
) -> dict[str, Any]:
    role = clean_text(payload.get("role")) or "unknown"
    if role not in {"internal", "customer", "channel", "unknown"}:
        return {
            "status": "blocked",
            "error_code": "invalid_sender_role",
            "alias_saved": False,
            "role": "unknown",
        }
    sender_display_name = clean_text(payload.get("sender_display_name"))
    person_name = clean_text(payload.get("person_name")) or "人工映射"
    alias_saved = False
    if sender_display_name and parse_bool(payload.get("add_alias"), True):
        conn.execute(
            """
            insert into people_aliases (person_name, alias, role, enabled)
            values (?, ?, ?, 1)
            on conflict(alias, role) do update set
              person_name = excluded.person_name,
              enabled = 1
            """,
            (person_name, sender_display_name, role),
        )
        conn.commit()
        alias_saved = True
    return {
        "status": "saved",
        "role": role,
        "alias_saved": alias_saved,
        "sender_label": "已保存人工映射" if alias_saved else "未保存别名",
    }


def real_trial_message_rows(
    conn: sqlite3.Connection, item_id: int | None = None
) -> list[dict[str, Any]]:
    if item_id is None:
        rows = conn.execute(
            """
            select rm.id, rm.sender_display_name, rm.sender_role, rm.sent_at,
                   rm.message_type, rm.content_text, ci.item_code, ci.risk_level,
                   ci.risk_tags_json
            from raw_messages rm
            left join candidate_item_messages cim on cim.raw_message_id = rm.id
            left join candidate_items ci on ci.id = cim.item_id
            order by rm.sent_at, rm.id, cim.evidence_order
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select rm.id, rm.sender_display_name, rm.sender_role, rm.sent_at,
                   rm.message_type, rm.content_text, ci.item_code, ci.risk_level,
                   ci.risk_tags_json
            from candidate_item_messages cim
            join raw_messages rm on rm.id = cim.raw_message_id
            left join candidate_items ci on ci.id = cim.item_id
            where cim.item_id = ?
            order by cim.evidence_order, rm.sent_at, rm.id
            """,
            (item_id,),
        ).fetchall()

    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        raw_id = int(row["id"])
        message = by_id.setdefault(
            raw_id,
            {
                "message_ref": f"m-{raw_id:04d}",
                "sent_at": str(row["sent_at"] or ""),
                "sender_display_name": safe_sender_display(row["sender_display_name"]),
                "sender_identity": safe_sender_role(row["sender_role"]),
                "sender_resolution": sender_resolution(
                    row["sender_display_name"], row["sender_role"]
                ),
                "message_type": str(row["message_type"] or "text"),
                "content": str(row["content_text"] or ""),
                "linked_candidate_codes": [],
                "has_risk": False,
                "risk_tags": [],
            },
        )
        if row["item_code"]:
            code = str(row["item_code"])
            if code not in message["linked_candidate_codes"]:
                message["linked_candidate_codes"].append(code)
        if row["risk_level"] and row["risk_level"] != "none":
            message["has_risk"] = True
        for tag in parse_json_list(row["risk_tags_json"]):
            if tag not in message["risk_tags"]:
                message["risk_tags"].append(tag)
    return list(by_id.values())


def sender_summary(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    senders: dict[tuple[str, str], dict[str, Any]] = {}
    for message in messages:
        key = (message["sender_display_name"], message["sender_identity"])
        row = senders.setdefault(
            key,
            {
                "sender_display_name": message["sender_display_name"],
                "sender_identity": message["sender_identity"],
                "sender_resolution": message["sender_resolution"],
                "message_count": 0,
            },
        )
        row["message_count"] += 1
    return list(senders.values())


def real_trial_template_items(config: AppConfig) -> list[dict[str, object]]:
    payload = real_trial_latest_items_payload(config)
    if payload.get("status") != "ok":
        return []
    items: list[dict[str, object]] = []
    for item in payload.get("items", []):
        items.append(
            {
                "id": int(item.get("id") or len(items) + 1),
                "item_code": str(item.get("item_code") or ""),
                "item_type": safe_item_type(item.get("item_type")),
                "status": str(item.get("status") or "pending"),
                "risk_level": safe_risk_level(item.get("risk_level")),
                "risk_tags": list(item.get("risk_tags") or []),
                "customer_name": "",
                "channel_name": "",
                "module_name": str(item.get("module_name") or ""),
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or ""),
                "suggested_downstream": safe_downstream(item.get("suggested_downstream")),
                "evidence": [],
                "reviews": [],
            }
        )
    return items


def safe_sender_display(value: Any) -> str:
    text = clean_text(value)
    lowered = text.lower()
    if not text or lowered.startswith("wxid") or lowered.startswith("gh_"):
        return "未解析微信名"
    return text


def safe_sender_role(value: Any) -> str:
    role = clean_text(value)
    return role if role in {"internal", "customer", "channel", "unknown"} else "unknown"


def sender_resolution(display_name: Any, role: Any) -> str:
    if safe_sender_display(display_name) == "未解析微信名":
        return "unresolved"
    return "manual_needed" if safe_sender_role(role) == "unknown" else "resolved"


def safe_item_type(value: Any) -> str:
    item_type = clean_text(value)
    return item_type if item_type in {"requirement", "bug", "consultation", "conclusion", "followup"} else "consultation"


def item_type_label(value: Any) -> str:
    return {
        "requirement": "客户需求",
        "bug": "问题 / Bug",
        "consultation": "咨询",
        "conclusion": "沟通结论",
        "followup": "待我方跟进",
    }.get(safe_item_type(value), "咨询")


def extraction_reason_for_item(item: dict[str, Any]) -> str:
    human_type = item_type_label(item.get("item_type"))
    source_message_count = int(item.get("source_message_count") or 0)
    risk_level = safe_risk_level(item.get("risk_level"))
    risk_text = "，含风险信号" if risk_level != "none" else ""
    return f"抽取理由：按消息语义归入{human_type}，关联 {source_message_count} 条来源消息{risk_text}，需人工确认。"


def safe_risk_level(value: Any) -> str:
    risk_level = clean_text(value)
    return risk_level if risk_level in {"none", "low", "high"} else "none"


def safe_downstream(value: Any) -> str:
    downstream = clean_text(value)
    return downstream if downstream in {"product", "tech", "ops", "manual"} else "manual"


def clean_trial_item_code(source_label: str, item_code: str) -> str:
    cleaned = "".join(ch for ch in item_code if ch.isalnum() or ch in {"-", "_"})
    return f"TRIAL-{source_label.upper()}-{cleaned or 'ITEM'}"


def clean_data_source(value: Any) -> str:
    source = clean_text(value)
    return "real_trial" if source == "real_trial" else "workspace"


def workspace_candidate_pool(
    conn: sqlite3.Connection, control_date: str
) -> list[dict[str, Any]]:
    return [
        item
        for item in load_daily_candidate_summaries(conn, control_date)
        if item["status"] != "rejected"
    ]


def resolve_candidate_pool_source(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> tuple[str, list[dict[str, object]]]:
    workspace_items = workspace_candidate_pool(conn, control_date)
    if workspace_items:
        return "workspace", workspace_items
    trial_items = real_trial_template_items(config)
    if trial_items:
        return "real_trial", trial_items
    return "workspace", []


def resolve_export_data_source(
    config: AppConfig,
    conn: sqlite3.Connection,
    export_date: str,
    requested: Any,
    *,
    include_pending: bool,
    confirmed_only: bool,
) -> str:
    requested_source = clean_text(requested)
    if requested_source:
        return clean_data_source(requested_source)
    workspace_items = load_template_items(
        conn,
        export_date,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
    )
    if workspace_items:
        return "workspace"
    trial_items = load_template_items(
        conn,
        export_date,
        include_pending=include_pending,
        confirmed_only=confirmed_only,
        source_items=real_trial_template_items(config),
    )
    return "real_trial" if trial_items else "workspace"


def resolve_draft_data_source(
    config: AppConfig,
    conn: sqlite3.Connection,
    control_date: str,
    requested: Any,
) -> str:
    requested_source = clean_text(requested)
    if requested_source:
        return clean_data_source(requested_source)
    workspace_items = workspace_candidate_pool(conn, control_date)
    if workspace_items:
        return "workspace"
    return "real_trial" if real_trial_template_items(config) else "workspace"


def data_source_label(data_source: str) -> str:
    return "最近试读候选" if data_source == "real_trial" else "当前工作台"


def draft_next_step(data_source: str, item_count: int, suggested_from_trial: bool) -> str:
    if suggested_from_trial and item_count > 0:
        return "发现最近试读候选；可生成试读草稿，人工审阅后再决定是否沉淀。"
    if item_count > 0:
        return "请人工审阅候选、风险和负责人后再生成本地草稿。"
    return "暂无可生成草稿的候选；请先完成试读或把候选加入待确认。"


def draft_source_items(
    config: AppConfig,
    conn: sqlite3.Connection,
    control_date: str,
    data_source: str,
) -> list[dict[str, object]]:
    if data_source == "real_trial":
        return real_trial_template_items(config)
    return [
        item
        for item in load_daily_candidate_summaries(conn, control_date)
        if item["status"] != "rejected"
    ]


def latest_draft_item_ids(conn: sqlite3.Connection, control_date: str) -> set[int]:
    latest_draft = latest_draft_for_date(conn, control_date)
    try:
        raw_ids = json.loads(str(latest_draft.get("item_ids_json") or "[]"))
    except json.JSONDecodeError:
        return set()
    ids: set[int] = set()
    for item_id in raw_ids:
        try:
            ids.add(int(item_id))
        except (TypeError, ValueError):
            continue
    return ids


def human_candidate_status(status: str, in_draft: bool) -> str:
    if in_draft:
        return "已进草稿"
    return {
        "pending": "待确认",
        "confirmed": "已确认",
        "rejected": "已驳回",
    }.get(status, "待确认")


def human_candidate_source_label(source: str) -> str:
    return "来自最近试读" if source == "real_trial" else "今日处理"


def human_candidate_risk_label(item: dict[str, object]) -> str:
    if safe_risk_level(item.get("risk_level")) == "none":
        return "无风险"
    tags = [redact_visible_text(tag) for tag in item.get("risk_tags", [])]
    return f"需先复核：{'、'.join(tags)}" if tags else "需先复核"


def human_candidate_owner_label(item: dict[str, object]) -> str:
    return clean_text(item.get("owner_name")) or "待指定负责人"


def human_candidate_downstream_label(value: Any) -> str:
    return {
        "product": "建议转产品",
        "tech": "建议转技术",
        "ops": "建议转运营",
        "manual": "待人工判断",
        "none": "待人工判断",
    }.get(clean_text(value), "待人工判断")


def human_candidate_reason(item: dict[str, object], source: str, in_draft: bool) -> str:
    if in_draft:
        return "这条候选已进入草稿，可继续润色后再转述。"
    if source == "real_trial":
        return redact_visible_text(
            item.get("extraction_reason")
            or "这条候选来自最近试读，建议先加入今日处理再确认。"
        )
    if clean_text(item.get("status")) == "confirmed":
        return "这条候选已进入今日处理，可继续补负责人和转述口径。"
    return "这条候选已进入今日处理，下一步请确认、驳回或改类型。"


def human_candidate_next_step(item: dict[str, object], source: str, in_draft: bool) -> str:
    status = clean_text(item.get("status")) or "pending"
    if in_draft:
        return "已进入草稿，可继续润色或整理转述摘要。"
    if source == "real_trial":
        return "先加入今日处理，再确认或生成草稿。"
    if status == "confirmed":
        return "可生成草稿日报或整理转述摘要。"
    return "先确认、驳回或改类型，再决定是否进入草稿。"


def candidate_action_label(source: str, status: str, in_draft: bool) -> str:
    if in_draft:
        return "查看草稿"
    if source == "real_trial":
        return "加入今日处理"
    if status == "confirmed":
        return "继续查看"
    return "确认处理"


def build_candidate_inbox_items(
    items: list[dict[str, object]], source: str, drafted_item_ids: set[int]
) -> list[dict[str, object]]:
    human_items: list[dict[str, object]] = []
    for item in items:
        item_id = int(item.get("id") or 0)
        status = "pending" if source == "real_trial" else (clean_text(item.get("status")) or "pending")
        in_draft = item_id in drafted_item_ids
        human_items.append(
            {
                "id": item_id,
                "display_id": str(item.get("item_code") or ""),
                "human_type": item_type_label(item.get("item_type")),
                "human_status": human_candidate_status(status, in_draft),
                "source_label": human_candidate_source_label(source),
                "action_label": candidate_action_label(source, status, in_draft),
                "summary_safe": redact_visible_text(
                    item.get("summary") or item.get("title") or ""
                ),
                "reason_safe": human_candidate_reason(item, source, in_draft),
                "risk_label": human_candidate_risk_label(item),
                "owner_label": human_candidate_owner_label(item),
                "next_step_label": human_candidate_next_step(item, source, in_draft),
                "downstream_label": human_candidate_downstream_label(
                    item.get("downstream") or item.get("suggested_downstream")
                ),
                "can_confirm": source == "workspace" and status == "pending",
                "can_reject": source == "workspace" and status == "pending",
                "can_edit_type": source == "workspace" and status != "rejected",
            }
        )
    return human_items


def candidate_inbox_summary_label(items: list[dict[str, object]]) -> str:
    if not items:
        return "当前没有待处理候选"
    pending_count = len([item for item in items if item["human_status"] == "待确认"])
    if pending_count:
        return f"还有 {pending_count} 条候选待确认"
    return f"当前有 {len(items)} 条候选可继续处理"


def candidate_inbox_source_hint(source: str, count: int) -> str:
    if source == "real_trial" and count > 0:
        return "当前直接显示最近试读候选，无需先切换数据来源。"
    if count > 0:
        return "当前直接显示今日处理里的候选，无需额外切换数据来源。"
    return "当前没有可处理候选；可先查看试读消息或补充今日处理。"


def candidate_inbox_primary_action(source: str, count: int) -> dict[str, str]:
    if source == "real_trial":
        return {
            "action": "import_to_workspace",
            "label": f"把 {count} 条候选加入今日处理" if count else "加入今日处理",
        }
    return {"action": "review_candidates", "label": "继续处理当前候选"}


def candidate_inbox_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, object]:
    source, raw_items = resolve_candidate_pool_source(config, conn, control_date)
    human_items = build_candidate_inbox_items(
        raw_items, source, latest_draft_item_ids(conn, control_date)
    )
    return {
        "title": "候选收件箱",
        "count": len(human_items),
        "summary_label": candidate_inbox_summary_label(human_items),
        "source_hint": candidate_inbox_source_hint(source, len(human_items)),
        "requires_source_switch": False,
        "primary_action": candidate_inbox_primary_action(source, len(human_items)),
        "empty_state_label": "当前没有候选；先去看消息或补充今天需要处理的事项。",
        "items": human_items,
        "source_key": source,
        "raw_items": raw_items,
    }


def human_task_title(template_id: str) -> str:
    return {
        "product_tech_summary": "给内部产品 / 技术同步",
        "daily_review": "给自己留今日复盘",
        "followup_checklist": "给自己列后续跟进",
    }.get(template_id, "整理转述摘要")


def human_task_subtitle(template_id: str) -> str:
    return {
        "product_tech_summary": "把最值得推进的候选整理成可直接复制的人话摘要。",
        "daily_review": "把今天的候选整理成一版给自己审阅的结果摘要。",
        "followup_checklist": "把接下来要继续推进的事项列成可执行清单。",
    }.get(template_id, "把当前候选整理成可直接复制的结果摘要。")


def transfer_copy_ready_lines(items: list[dict[str, object]]) -> list[str]:
    if not items:
        return ["当前还没有可转述候选，请先确认今天最需要处理的事项。"]
    return [
        f"{item.get('item_code', '')}｜{item_type_label(item.get('item_type'))}｜{redact_visible_text(item.get('summary') or item.get('title') or '')}"
        for item in items[:3]
    ]


def transfer_task_payload(
    template_id: str, data_source: str, items: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "task_title": human_task_title(template_id),
        "task_subtitle": human_task_subtitle(template_id),
        "candidate_count": len(items),
        "candidate_count_label": f"当前有 {len(items)} 条候选可转述",
        "source_label": (
            "默认直接使用最近试读候选"
            if data_source == "real_trial"
            else "默认直接使用今日处理候选"
        ),
        "copy_ready": bool(items),
        "copy_ready_lines": transfer_copy_ready_lines(items),
        "primary_action_label": "复制人话摘要",
        "task_options": [
            {
                "key": "customer_reply",
                "label": "给客户回复",
                "hint": "先整理一版可直接发出的回复思路。",
            },
            {
                "key": "internal_sync",
                "label": "给内部产品 / 技术同步",
                "hint": "把最需要推进的事项同步给内部同事。",
            },
            {
                "key": "self_recap",
                "label": "给自己留今日复盘",
                "hint": "留下今天最重要的候选和下一步动作。",
            },
        ],
    }


def draft_link_items(
    items: list[dict[str, object]], data_source: str
) -> list[dict[str, object]]:
    target = "real_trial_messages" if data_source == "real_trial" else "workspace_candidate"
    return [
        {
            "item_id": int(item.get("id") or 0),
            "item_code": str(item.get("item_code") or ""),
            "item_type": str(item.get("item_type") or ""),
            "status": str(item.get("status") or ""),
            "risk_level": str(item.get("risk_level") or "none"),
            "target": target,
        }
        for item in items
    ]


def render_machine_draft_preview(
    control_date: str, data_source: str, items: list[dict[str, object]]
) -> str:
    source_label = "最近真实试读" if data_source == "real_trial" else "当前工作台"
    lines = [
        f"# {control_date} 草稿日报 / 机器初稿",
        "",
        f"- 数据源：{source_label}",
        f"- 候选数：{len(items)}",
        f"- 风险数：{len([item for item in items if item['risk_level'] != 'none'])}",
        "- 状态：机器初稿 / 待审阅",
        "- 正式写入：禁用 / 未写入",
        "- 安全说明：本地机器初稿，需人工审阅，不能直接外发或沉淀到正式区。",
        "",
        "## 候选条目",
        "",
    ]
    if not items:
        lines.extend(["暂无", ""])
    else:
        for item in items:
            lines.extend(
                [
                    f"- {item['item_code']}｜{item['item_type']}｜{item['status']}｜风险：{item['risk_level']}",
                    f"  - 摘要：{redact_visible_text(item.get('summary', ''))}",
                    f"  - 定位：{('最近真实试读消息链' if data_source == 'real_trial' else '当前工作台候选详情')}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_machine_draft(
    config: AppConfig,
    conn: sqlite3.Connection,
    control_date: str,
    data_source: str,
    preview_markdown: str,
    items: list[dict[str, object]],
) -> Path:
    export_dir = Path(config.root) / config.export.directory / "daily_machine_drafts"
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{control_date} {data_source} 草稿日报机器初稿.md"
    file_path.write_text(preview_markdown, encoding="utf-8")
    item_ids = [int(item.get("id") or 0) for item in items]
    summary = {
        "candidate_count": len(items),
        "risk_count": len([item for item in items if item["risk_level"] != "none"]),
        "data_source": data_source,
        "formal_write_enabled": False,
    }
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
    return file_path


def config_center_payload(config: AppConfig) -> dict[str, Any]:
    enabled_whitelist_count = len(
        [s for s in config.sessions if s.enabled and s.is_whitelisted]
    )
    readiness = wx_cli_readiness(config)
    return {
        "status": {
            "mode": config.wx_cli.mode,
            "real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "wx_cli_status": readiness["status"],
            "enabled_whitelist_count": enabled_whitelist_count,
            "latest_trial": latest_real_trial_payload(config),
        },
        "editable": {
            "sessions": [
                {
                    "external_id": session.external_id,
                    "display_name": session.display_name,
                    "customer_name": session.customer_name,
                    "channel_name": session.channel_name,
                    "module_name": session.module_name,
                    "owner_name": session.owner_name,
                    "customer_stage": session.customer_stage,
                    "group_type": session.group_type,
                    "common_contacts": list(session.common_contacts),
                    "reply_notes": session.reply_notes,
                    "is_whitelisted": bool(session.is_whitelisted),
                    "enabled": bool(session.enabled),
                }
                for session in config.sessions
            ],
            "internal_people": [
                {
                    "person_name": person.person_name,
                    "aliases": list(person.aliases),
                }
                for person in config.internal_people
            ],
            "risk": {
                "keywords": list(config.risk.keywords),
                "sensitive_keywords": list(config.risk.sensitive_keywords),
            },
            "trial_defaults": {
                "lookback_hours": min(max(1, int(config.wx_cli.real_lookback_hours)), 2),
                "limit": min(max(1, int(config.wx_cli.real_limit)), 50),
                "start_at": config.wx_cli.real_start_at,
                "end_at": config.wx_cli.real_end_at,
            },
        },
        "safety": {
            "default_real_read_enabled": False,
            "save_triggers_collection": False,
            "requires_confirmation": True,
            "max_limit": 50,
            "max_lookback_hours": 2,
            "requires_single_enabled_whitelist": True,
            "fixture_service_notice": config.wx_cli.mode != "real",
        },
        "save_target": "config/app.yaml",
    }


def save_config_center_payload(config: AppConfig, payload: dict[str, Any]) -> dict[str, Any]:
    sessions_payload = payload.get("sessions")
    if isinstance(sessions_payload, list):
        config.sessions = [
            SessionConfig(
                external_id=clean_text(item.get("external_id")),
                display_name=clean_text(item.get("display_name")),
                customer_name=clean_text(item.get("customer_name")),
                channel_name=clean_text(item.get("channel_name")),
                module_name=clean_text(item.get("module_name")),
                owner_name=clean_text(item.get("owner_name")),
                customer_stage=clean_text(item.get("customer_stage")),
                group_type=clean_text(item.get("group_type")),
                common_contacts=clean_text_list(item.get("common_contacts")),
                reply_notes=clean_text(item.get("reply_notes")),
                is_whitelisted=bool(item.get("is_whitelisted", True)),
                enabled=bool(item.get("enabled", True)),
            )
            for item in sessions_payload
            if isinstance(item, dict)
            and clean_text(item.get("external_id"))
            and clean_text(item.get("display_name"))
        ]

    people_payload = payload.get("internal_people")
    if isinstance(people_payload, list):
        config.internal_people = [
            PersonConfig(
                person_name=clean_text(item.get("person_name")),
                aliases=[
                    clean_text(alias)
                    for alias in item.get("aliases", [])
                    if clean_text(alias)
                ],
            )
            for item in people_payload
            if isinstance(item, dict) and clean_text(item.get("person_name"))
        ]

    risk_payload = payload.get("risk", {})
    if isinstance(risk_payload, dict):
        config.risk = RiskConfig(
            keywords=clean_text_list(risk_payload.get("keywords")),
            sensitive_keywords=clean_text_list(risk_payload.get("sensitive_keywords")),
        )

    trial_defaults = payload.get("trial_defaults", {})
    if isinstance(trial_defaults, dict):
        config.wx_cli.real_lookback_hours = clamp_int(
            trial_defaults.get("lookback_hours"), minimum=1, maximum=2, default=2
        )
        config.wx_cli.real_limit = clamp_int(
            trial_defaults.get("limit"), minimum=1, maximum=50, default=50
        )
        config.wx_cli.real_start_at = clean_text(trial_defaults.get("start_at"))
        config.wx_cli.real_end_at = clean_text(trial_defaults.get("end_at"))

    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": "saved",
        "real_read_enabled": False,
        "saved_to": "config/app.yaml",
        "editable": config_center_payload(config)["editable"],
    }


def real_trial_run_plan(config: AppConfig, payload: dict[str, Any]) -> dict[str, Any]:
    confirmed = bool(payload.get("confirmed", False))
    limit = clamp_int(payload.get("limit"), minimum=1, maximum=50, default=50)
    preset = clean_text(payload.get("preset"))
    start_at = clean_text(payload.get("start_at"))
    end_at = clean_text(payload.get("end_at"))
    lookback_raw = clean_text(payload.get("lookback_hours"))
    enabled_whitelist = [
        session
        for session in config.sessions
        if session.enabled and session.is_whitelisted
    ]
    if not confirmed:
        return {
            "status": "needs_confirmation",
            "will_run": False,
            "error_code": "confirmation_required",
            "message": "开始试读前需要确认范围和禁止项。",
        }
    if len(enabled_whitelist) != 1:
        return {
            "status": "blocked",
            "will_run": False,
            "error_code": "real_trial_whitelist_count_invalid",
            "message": "真实试读要求启用白名单会话数量必须等于 1。",
        }
    try:
        requested_limit = int(payload.get("limit", limit) or limit)
    except (TypeError, ValueError):
        return {
            "status": "blocked",
            "will_run": False,
            "error_code": "real_trial_limit_invalid",
            "message": "真实试读条数必须是数字。",
        }
    if requested_limit > 50:
        return {
            "status": "blocked",
            "will_run": False,
            "error_code": "real_trial_limit_too_large",
            "message": "真实试读条数上限不能超过 50。",
        }
    if preset != "recent50" and not lookback_raw and not (start_at and end_at):
        return {
            "status": "blocked",
            "will_run": False,
            "error_code": "real_trial_time_range_required",
            "message": "真实试读需要起止日期时间，或选择最近50条快捷项。",
        }
    return {
        "status": "dry_run_ready",
        "will_run": False,
        "error_code": "real_trial_run_not_executed_in_this_task",
        "message": "安全检查通过；本轮开发只提供安全壳，未执行真实读取。",
        "scope": {
            "enabled_whitelist_count": 1,
            "limit": limit,
            "preset": preset,
            "start_at": start_at,
            "end_at": end_at,
            "lookback_hours": lookback_raw,
            "no_external_send": True,
            "no_auto_reply": True,
            "no_formal_write": True,
        },
    }


def write_config_center_yaml(config: AppConfig) -> None:
    payload = {
        "app": {"host": config.app.host, "port": config.app.port},
        "database": {"path": config.database.path},
        "wx_cli": {
            "mode": config.wx_cli.mode,
            "binary": config.wx_cli.binary,
            "timeout_seconds": config.wx_cli.timeout_seconds,
            "fixture_dir": config.wx_cli.fixture_dir,
            "real_read_enabled": False,
            "real_allowed_session": config.wx_cli.real_allowed_session,
            "real_lookback_hours": min(max(1, int(config.wx_cli.real_lookback_hours)), 2),
            "real_limit": min(max(1, int(config.wx_cli.real_limit)), 50),
            "real_start_at": config.wx_cli.real_start_at,
            "real_end_at": config.wx_cli.real_end_at,
        },
        "collector": {
            "interval_minutes": config.collector.interval_minutes,
            "lookback_minutes": config.collector.lookback_minutes,
        },
        "export": {"directory": config.export.directory},
        "sessions": [
            {
                "external_id": session.external_id,
                "display_name": session.display_name,
                "customer_name": session.customer_name,
                "channel_name": session.channel_name,
                "module_name": session.module_name,
                "owner_name": session.owner_name,
                "customer_stage": session.customer_stage,
                "group_type": session.group_type,
                "common_contacts": list(session.common_contacts),
                "reply_notes": session.reply_notes,
                "is_whitelisted": bool(session.is_whitelisted),
                "enabled": bool(session.enabled),
            }
            for session in config.sessions
        ],
        "internal_people": [
            {"person_name": person.person_name, "aliases": list(person.aliases)}
            for person in config.internal_people
        ],
        "risk": {
            "keywords": list(config.risk.keywords),
            "sensitive_keywords": list(config.risk.sensitive_keywords),
        },
    }
    target = Path(config.root) / "config" / "app.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    except Exception:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    target.write_text(text, encoding="utf-8")


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def clean_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\r", "\n").split("\n")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [clean_text(item) for item in values if clean_text(item)]


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def parse_json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def latest_real_trial_db(data_dir: Path) -> Path | None:
    if not data_dir.exists():
        return None
    candidates = [
        path
        for path in data_dir.glob("real_trial_recent50_*.sqlite3")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def read_real_trial_stats(db_path: Path) -> dict[str, Any]:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        raw_count = scalar_count(conn, "raw_messages")
        candidate_count = scalar_count(conn, "candidate_items")
        risk_count = conn.execute(
            "select count(*) from candidate_items where risk_level != 'none'"
        ).fetchone()[0]
        status_rows = conn.execute(
            """
            select status, count(*) as count
            from candidate_items
            group by status
            """
        ).fetchall()
        run = conn.execute(
            """
            select mode, started_at, finished_at, status, raw_messages_seen,
                   raw_messages_inserted, raw_messages_duplicated,
                   candidate_items_created, candidate_items_updated, error_code
            from collection_runs
            order by id desc
            limit 1
            """
        ).fetchone()
        collection_run = dict(run) if run else {}
        return {
            "trial_finished_at": str(collection_run.get("finished_at") or ""),
            "raw_count": int(raw_count),
            "candidate_count": int(candidate_count),
            "risk_count": int(risk_count),
            "candidate_status_counts": {
                str(row["status"]): int(row["count"]) for row in status_rows
            },
            "collection_run": collection_run,
        }
    finally:
        conn.close()


def scalar_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"select count(*) from {table_name}").fetchone()[0])


def source_label_for_trial(path: Path) -> str:
    return "recent50" if path.name.startswith("real_trial_recent50_") else "real_trial"


def real_trial_export_dir(config: AppConfig, db_path: Path) -> Path:
    return Path(config.root) / "exports" / db_path.stem


def relative_to_root(config: AppConfig, path: Path) -> str:
    try:
        return path.relative_to(config.root).as_posix()
    except ValueError:
        return path.name


def save_review(
    conn: sqlite3.Connection,
    item_id: int,
    review_status: str,
    payload: dict[str, Any],
    priority: str,
    downstream: str,
) -> None:
    conn.execute(
        """
        insert into manual_reviews (
          item_id, review_status, owner_name, priority, downstream, note,
          reviewed_by
        )
        values (?, ?, ?, ?, ?, ?, 'local')
        """,
        (
            item_id,
            review_status,
            str(payload.get("owner_name", "")),
            priority,
            downstream,
            str(payload.get("note", "")),
        ),
    )
    conn.execute(
        """
        update candidate_items
        set status = ?, updated_at = current_timestamp
        where id = ?
        """,
        (review_status, item_id),
    )
    conn.commit()
