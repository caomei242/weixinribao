from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .collector import collect_messages, collect_normalized_messages, latest_run
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
from .wx_cli_adapter import (
    WxCliUnavailable,
    fetch_group_roster_members,
    map_history_payload,
    run_wx_cli_json,
    test_connection,
    wx_cli_readiness,
)

LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS = 2
LEGACY_REAL_TRIAL_MAX_LIMIT = 50
CONFIGURABLE_REAL_TRIAL_HARD_SAFETY_DAYS = 365
CONFIGURABLE_REAL_TRIAL_HARD_MAX_GROUPS = 50
CONFIGURABLE_REAL_TRIAL_HARD_MAX_TOTAL_MESSAGES = 10000
CONFIGURABLE_REAL_TRIAL_HARD_MAX_MESSAGES_PER_GROUP = 1000
CONFIGURABLE_REAL_TRIAL_HARD_MAX_BATCHES = 12
CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_GROUPS = 20
CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_TOTAL_MESSAGES = 5000
CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_MESSAGES_PER_GROUP = 500
CONFIGURABLE_REAL_TRIAL_DEFAULT_BATCH_LIMIT = 1
CONFIGURABLE_REAL_TRIAL_PRESETS = {
    "30d",
    "configurable",
    "configurable_window",
    "expanded",
    "expanded30d",
    "expanded_30d",
    "last30days",
    "last_30_days",
    "multi_group_30d",
    "recent30days",
}
ALL_WECHAT_GROUP_SCOPE_ALIASES = {
    "all_wechat_groups",
    "all_wechat_group",
    "allwechatgroups",
    "allwechatgroup",
    "all_detected_groups",
    "all_detected_wechat_groups",
    "alldetectedgroups",
    "alldetectedwechatgroups",
    "all_wechat_chatrooms",
    "allwechatchatrooms",
    "wechat_groups_all",
    "wechatgroupsall",
}
GROUP_DISPLAY_PLACEHOLDER = "群名待解析"
READABLE_SESSION_NAME_KEYS = (
    "display_name",
    "name",
    "nickname",
    "remark",
    "title",
    "alias",
    "chatroom_name",
    "group_name",
    "room_name",
    "nickName",
    "remarkName",
)


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
        readiness = wx_cli_readiness(config)
        return {
            **safe_status_payload(config),
            "latest_run": latest_run(conn),
            "connection": safe_status_connection_payload(readiness),
            "wx_cli_ready": safe_wx_cli_public_payload(readiness),
        }

    @app.get("/api/inbox/v1")
    def inbox_v1(control_date: Optional[str] = None):
        return inbox_v1_payload(config, conn, control_date or date.today().isoformat())

    @app.get("/api/daily-center")
    def daily_center(control_date: Optional[str] = None):
        return daily_center_payload(config, conn, control_date or date.today().isoformat())

    @app.get("/api/daily-center/generation-status")
    def daily_generation_status(control_date: Optional[str] = None):
        return daily_generation_status_payload(
            config, conn, control_date or date.today().isoformat()
        )

    @app.post("/api/daily-center/generate")
    def daily_generate(payload: Optional[dict[str, Any]] = None):
        return generate_daily_report_payload(config, conn, payload or {})

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

    @app.get("/api/customer-options")
    def customer_options():
        return customer_options_api_payload(config)

    @app.get("/api/customer-suggestions")
    def customer_suggestions(group_name: Optional[str] = None):
        return monitor_group_customer_suggestion_payload(config, group_name or "")

    @app.get("/api/customers/suggestions")
    def customers_suggestions(group_name: Optional[str] = None):
        return monitor_group_customer_suggestion_payload(config, group_name or "")

    @app.get("/api/monitor-groups/customer-suggestion")
    def monitor_group_customer_suggestion(group_name: Optional[str] = None):
        return monitor_group_customer_suggestion_payload(config, group_name or "")

    @app.get("/api/monitor-groups/customer-suggestions")
    def monitor_group_customer_suggestions(group_name: Optional[str] = None):
        return monitor_group_customer_suggestion_payload(config, group_name or "")

    @app.post("/api/monitor-groups")
    def monitor_group_create(payload: dict[str, Any]):
        return save_monitor_group_payload(config, payload, conn=conn)

    @app.get("/api/monitor-groups/{group_id}")
    def monitor_group_detail(group_id: str):
        payload = monitor_group_detail_payload(config, group_id, conn)
        if payload["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return payload

    @app.post("/api/monitor-groups/{group_id}/refresh-members")
    def monitor_group_refresh_members(group_id: str):
        result = refresh_monitor_group_members_payload(config, group_id, conn)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/monitor-groups/{group_id}/sync-roster")
    def monitor_group_sync_roster(group_id: str, payload: Optional[dict[str, Any]] = None):
        result = sync_monitor_group_roster_payload(config, group_id, payload or {}, conn)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.put("/api/monitor-groups/{group_id}")
    def monitor_group_update(group_id: str, payload: dict[str, Any]):
        result = save_monitor_group_payload(config, payload, group_id=group_id, conn=conn)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/monitor-groups/{group_id}/disable")
    def monitor_group_disable(group_id: str):
        result = disable_monitor_group_payload(config, group_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/monitor-groups/{group_id}/archive")
    def monitor_group_archive(group_id: str):
        result = archive_monitor_group_payload(config, group_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.post("/api/monitor-groups/{group_id}/delete")
    def monitor_group_delete(group_id: str, payload: Optional[dict[str, Any]] = None):
        result = delete_monitor_group_payload(config, group_id, payload or {})
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="monitor group not found")
        return result

    @app.get("/api/internal-people")
    def internal_people():
        return internal_people_payload(config, conn)

    @app.post("/api/internal-people/suggestions")
    def internal_people_suggestions(payload: dict[str, Any]):
        return internal_people_suggestions_payload(config, conn, payload)

    @app.get("/api/internal-people/suggestions")
    def internal_people_suggestions_get(
        query: Optional[str] = None,
        display_name: Optional[str] = None,
        name: Optional[str] = None,
        wechat_id: Optional[str] = None,
    ):
        return internal_people_suggestions_payload(
            config,
            conn,
            {
                "query": query,
                "display_name": display_name,
                "name": name,
                "wechat_id": wechat_id,
            },
        )

    @app.post("/api/internal-people")
    def internal_people_create(payload: dict[str, Any]):
        return save_internal_person_payload(config, conn, payload)

    @app.put("/api/internal-people/{person_id}")
    def internal_people_update(person_id: str, payload: dict[str, Any]):
        result = save_internal_person_payload(config, conn, payload, person_id=person_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="person not found")
        return result

    @app.post("/api/internal-people/{person_id}/disable")
    def internal_people_disable(person_id: str):
        result = disable_internal_person_payload(config, conn, person_id)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="person not found")
        return result

    @app.get("/api/messages/v1")
    def messages_v1(group_id: Optional[str] = None):
        return messages_v1_payload(config, conn, group_id or "all")

    @app.get("/api/windows-readiness")
    def windows_readiness():
        return windows_readiness_payload(config)

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
        return safe_wx_cli_public_payload(test_connection(config))

    @app.get("/api/wx-cli/readiness")
    def wx_cli_ready():
        return safe_wx_cli_public_payload(wx_cli_readiness(config))

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

    @app.post("/api/real-trial/persistent-control")
    def real_trial_persistent_control(payload: Optional[dict[str, Any]] = None):
        return persistent_real_read_control_payload(config, payload or {}, conn)

    @app.get("/api/config-center")
    def config_center():
        return config_center_payload(config, conn)

    @app.post("/api/config-center")
    def save_config_center(payload: dict[str, Any]):
        return save_config_center_payload(config, payload, conn)

    @app.post("/api/real-trial/run")
    def real_trial_run(payload: dict[str, Any]):
        return real_trial_run_plan(config, payload, conn=conn)

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


def safe_wx_cli_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": clean_text(payload.get("status")) or "unknown",
        "error_code": clean_text(payload.get("error_code")),
        "message": redact_visible_text(clean_text(payload.get("message"))),
        "command": clean_text(payload.get("command")),
        "returncode": clean_text(payload.get("returncode")),
        "wx_cli_status": clean_text(payload.get("wx_cli_status")),
        "binary_configured": parse_bool(payload.get("binary_configured"), False),
        "is_executable": parse_bool(payload.get("is_executable"), False),
        "session_count": clean_text(payload.get("session_count")),
        "next_action": clean_text(payload.get("next_action")),
        "binary_path_returned": False,
        "configured_binary_returned": False,
    }


def safe_status_connection_payload(readiness: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "status": "not_checked",
        "error_code": "connection_test_not_run",
        "message": "状态摘要不执行会话探测；需要时请用户显式触发连接测试。",
        "wx_cli_status": readiness.get("status"),
        "binary_configured": readiness.get("binary_configured"),
        "is_executable": readiness.get("is_executable"),
        "session_count": "0",
        "next_action": readiness.get("next_action"),
    }
    return safe_wx_cli_public_payload(payload)


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
    drafted_ids = latest_draft_item_ids(conn, control_date)
    monitor_count = daily_center_monitor_group_count(config)
    new_issue_count = len(candidates)
    historical_count = len(historical_items)
    report_status_label = "已生成" if has_report else "未生成"
    settlement_status_label = (
        "已沉淀" if has_draft else ("待沉淀" if has_report else "暂无可沉淀")
    )
    today_top_followups = daily_followup_items_payload(
        candidates[:5], drafted_ids, "today_top_followups"
    )
    unfinished_followups = daily_followup_items_payload(
        [
            item
            for item in candidates
            if candidate_home_status_label(item, drafted_ids) in {"待确认", "已确认跟进"}
        ],
        drafted_ids,
        "unfinished_followups",
    )
    historical_unfinished = daily_followup_items_payload(
        historical_items, drafted_ids, "historical_unfinished"
    )
    generation_status = daily_generation_status_payload(config, conn, control_date)
    return {
        "status": "ok",
        "page_title": "日报中心",
        "control_date": control_date,
        "source": {
            "label": "本地候选与本地草稿",
            "new_issue_count": new_issue_count,
            "unfinished_followup_count": len(unfinished_followups),
            "historical_unfinished_count": len(historical_unfinished),
            "monitor_group_count": monitor_count,
            "formal_write_enabled": False,
        },
        "summary": {
            "report_status_label": report_status_label,
            "settlement_status_label": settlement_status_label,
            "monitor_group_count": monitor_count,
            "new_issue_count": new_issue_count,
            "historical_unfollowed_count": historical_count,
            "unfinished_followup_count": len(unfinished_followups),
            "historical_unfinished_count": len(historical_unfinished),
        },
        "today_top_followups": today_top_followups,
        "unfinished_followups": unfinished_followups,
        "historical_unfinished": historical_unfinished,
        "today_focus": daily_center_today_focus_payload(
            control_date,
            candidates,
            historical_items,
            monitor_count,
            latest_run(conn),
            has_report,
        ),
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
            "report_full_text": report_body,
            "report_human_text": report_body,
            "source_label": "本地候选与本地草稿",
            "empty_state_label": (
                "" if has_report else "当前还没有可展示日报；可先生成本地机器初稿。"
            ),
            "body_source_label": "本地候选生成",
        },
        "report_full_text": report_body,
        "report_human_text": report_body,
        "generation_status": generation_status,
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


def daily_followup_items_payload(
    items: list[dict[str, Any]], drafted_ids: set[int], source: str
) -> list[dict[str, Any]]:
    source_label = {
        "today_top_followups": "今天最要跟进",
        "unfinished_followups": "未完成跟进事项",
        "historical_unfinished": "历史未跟进",
    }.get(source, "跟进事项")
    rows: list[dict[str, Any]] = []
    for item in items:
        label = candidate_home_status_label(item, drafted_ids)
        summary_text = local_ui_display_text(item.get("summary") or item.get("title") or "")
        customer_label = local_ui_display_text(item.get("customer_name") or "未标客户")
        module_label = local_ui_display_text(item.get("module_name") or "未标模块")
        raw_group_label = (
            item.get("group_name")
            or item.get("session_display_name")
            or item.get("session_name")
        )
        group_fields = (
            local_group_display_fields(raw_group_label, source="candidate_item")
            if clean_text(raw_group_label)
            else {
                "group_label": "",
                "group_label_safe": "",
                "group_label_status": "not_provided",
                "group_label_reason_code": "",
                "group_label_source_error_code": "",
            }
        )
        rows.append(
            {
                "item_id": int(item.get("id") or 0),
                "display_id": local_ui_display_text(item.get("item_code")),
                "display_id_safe": redact_visible_text(item.get("item_code")),
                "title": local_ui_display_text(item.get("title")),
                "summary": summary_text,
                "summary_safe": redact_visible_text(summary_text),
                "human_status": label,
                "home_status_label": label,
                "action_label": candidate_home_action_label(label),
                "risk_label": human_candidate_risk_label(item),
                "source": source,
                "source_label": source_label,
                "customer_label": customer_label,
                "customer_label_safe": redact_visible_text(customer_label),
                "module_label": module_label,
                "module_label_safe": redact_visible_text(module_label),
                **group_fields,
            }
        )
    return rows


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


def daily_center_today_focus_payload(
    control_date: str,
    candidates: list[dict[str, Any]],
    historical_items: list[dict[str, Any]],
    monitor_count: int,
    latest_collection: dict[str, Any],
    has_report: bool,
) -> dict[str, Any]:
    priority_items = list(candidates[:3])
    if len(priority_items) < 3:
        priority_items.extend(historical_items[: 3 - len(priority_items)])
    failure_reason = clean_text(latest_collection.get("error_code")) or clean_text(
        latest_collection.get("error_message")
    )
    headline = (
        f"今天优先跟进 {len(priority_items)} 条"
        if priority_items
        else "今天暂无必须跟进事项"
    )
    return {
        "title": "今天最要跟进",
        "headline": headline,
        "status_label": "需要处理" if priority_items else "暂无新负担",
        "control_date": control_date,
        "monitor_group_status_label": (
            f"{monitor_count} 个监控群纳入日报" if monitor_count else "暂无已验证日报监控群"
        ),
        "new_issue_count": len(candidates),
        "historical_unfollowed_count": len(historical_items),
        "report_status_label": "日报已生成" if has_report else "日报未生成",
        "failure_reason_label": (
            f"最近采集失败原因：{redact_visible_text(failure_reason)}"
            if failure_reason
            else ""
        ),
        "items": [
            {
                "display_id": local_ui_display_text(item.get("item_code")),
                "display_id_safe": redact_visible_text(item.get("item_code")),
                "title": local_ui_display_text(item.get("title")),
                "summary": local_ui_display_text(item.get("summary") or item.get("title") or ""),
                "summary_safe": redact_visible_text(
                    item.get("summary") or item.get("title") or ""
                ),
                **(
                    local_group_display_fields(
                        item.get("group_name")
                        or item.get("session_display_name")
                        or item.get("session_name"),
                        source="candidate_item",
                    )
                    if clean_text(
                        item.get("group_name")
                        or item.get("session_display_name")
                        or item.get("session_name")
                    )
                    else {
                        "group_label": "",
                        "group_label_safe": "",
                        "group_label_status": "not_provided",
                        "group_label_reason_code": "",
                        "group_label_source_error_code": "",
                    }
                ),
                "home_status_label": candidate_home_status_label(item, set()),
                "action_label": candidate_home_action_label(
                    candidate_home_status_label(item, set())
                ),
            }
            for item in priority_items
        ],
        "primary_action": {
            "label": "先处理这些跟进项" if priority_items else "生成/刷新日报",
            "enabled": True,
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


def daily_generation_status_payload(
    config: AppConfig, conn: sqlite3.Connection, control_date: str
) -> dict[str, Any]:
    draft = latest_draft_for_date(conn, control_date)
    data_source = resolve_draft_data_source(config, conn, control_date, None)
    item_count = len(draft_source_items(config, conn, control_date, data_source))
    generated = bool(draft)
    feedback_state = "success" if generated else "idle"
    return {
        "status": "generated" if generated else "idle",
        "feedback_state": feedback_state,
        "running": False,
        "success": generated,
        "failed": False,
        "status_label": "已生成，可查看日报" if generated else "等待生成",
        "control_date": control_date,
        "started_at": clean_text(draft.get("generated_at")) if draft else "",
        "finished_at": clean_text(draft.get("generated_at")) if draft else "",
        "data_source": data_source,
        "data_source_label": data_source_label(data_source),
        "candidate_count": item_count,
        "next_step_label": (
            "可继续审阅或重新生成" if generated else "点击生成后会立即返回进度"
        ),
        "retry_available": True,
        "error_code": "",
        "report_preserved": generated,
        "old_report_preserved": generated,
        "safety": {
            "formal_write_enabled": False,
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        },
    }


def generate_daily_report_payload(
    config: AppConfig, conn: sqlite3.Connection, body: dict[str, Any]
) -> dict[str, Any]:
    control_date = str(body.get("control_date") or date.today().isoformat())
    requested_source = body.get("data_source")
    data_source = resolve_draft_data_source(config, conn, control_date, requested_source)
    started_at = now_local_iso()
    latest_before = latest_draft_for_date(conn, control_date)
    items = draft_source_items(config, conn, control_date, data_source)
    if not items and latest_before:
        return {
            "status": "generated",
            "feedback_state": "success",
            "running": False,
            "success": True,
            "failed": False,
            "status_label": "没有新候选，已保留原日报正文",
            "control_date": control_date,
            "started_at": started_at,
            "finished_at": now_local_iso(),
            "data_source": data_source,
            "data_source_label": data_source_label(data_source),
            "candidate_count": 0,
            "file_path": relative_to_root(
                config, Path(clean_text(latest_before.get("file_path")))
            ),
            "preserved_previous_report": True,
            "old_report_preserved": True,
            "report_text_cleared": False,
            "next_step_label": "可继续查看原日报，或等新候选出现后再生成。",
            "retry_available": True,
            "error_code": "",
            "safety": {
                "formal_write_enabled": False,
                "save_triggers_collection": False,
                "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            },
        }
    try:
        preview_markdown = render_machine_draft_preview(control_date, data_source, items)
        file_path = write_machine_draft(
            config, conn, control_date, data_source, preview_markdown, items
        )
    except Exception:
        return {
            "status": "failed",
            "feedback_state": "failed",
            "running": False,
            "success": False,
            "failed": True,
            "status_label": "生成失败，可重试",
            "control_date": control_date,
            "started_at": started_at,
            "finished_at": now_local_iso(),
            "data_source": data_source,
            "data_source_label": data_source_label(data_source),
            "candidate_count": len(items),
            "error_code": "daily_generation_failed",
            "next_step_label": "请重试；如仍失败，再查看本地日志。",
            "retry_available": True,
            "preserved_previous_report": bool(latest_before),
            "old_report_preserved": bool(latest_before),
            "report_text_cleared": False,
            "safety": {
                "formal_write_enabled": False,
                "save_triggers_collection": False,
                "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            },
        }
    return {
        "status": "generated",
        "feedback_state": "success",
        "running": False,
        "success": True,
        "failed": False,
        "status_label": "已生成，可查看日报",
        "control_date": control_date,
        "started_at": started_at,
        "finished_at": now_local_iso(),
        "data_source": data_source,
        "data_source_label": data_source_label(data_source),
        "candidate_count": len(items),
        "file_path": relative_to_root(config, file_path),
        "preserved_previous_report": bool(latest_before),
        "old_report_preserved": bool(latest_before),
        "report_text_cleared": False,
        "next_step_label": "请审阅日报正文；正式沉淀仍需人工确认。",
        "retry_available": True,
        "error_code": "",
        "safety": {
            "formal_write_enabled": False,
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
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
        primary_owner_name(session),
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
        "group_owner": primary_owner_name(session),
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
            "lookback_hours": min(
                max(1, int(config.wx_cli.real_lookback_hours)),
                LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
            ),
            "limit": min(
                max(1, int(config.wx_cli.real_limit)),
                LEGACY_REAL_TRIAL_MAX_LIMIT,
            ),
            "expanded_trial": expanded_real_trial_contract_payload(config),
            "persistent_authorization": persistent_real_read_contract_payload(config),
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
                max(1, int(config.wx_cli.real_lookback_hours)),
                LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
            ),
            "real_limit": min(
                max(1, int(config.wx_cli.real_limit)),
                LEGACY_REAL_TRIAL_MAX_LIMIT,
            ),
            "expanded_trial": expanded_real_trial_contract_payload(config),
            "persistent_authorization": persistent_real_read_contract_payload(config),
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


def latest_real_trial_config_center_summary(config: AppConfig) -> dict[str, Any]:
    latest = latest_real_trial_payload(config)
    return {
        "status": latest.get("status", "not_found"),
        "mode": latest.get("mode", "real"),
        "source_label": latest.get("source_label", ""),
        "trial_finished_at": latest.get("trial_finished_at", ""),
        "current_service_mode": latest.get("current_service_mode", config.wx_cli.mode),
        "current_service_is_real": bool(latest.get("current_service_is_real")),
        "default_real_read_enabled": bool(latest.get("default_real_read_enabled")),
        "fixture_service_notice": bool(latest.get("fixture_service_notice")),
        "raw_count": int(latest.get("raw_count") or 0),
        "candidate_count": int(latest.get("candidate_count") or 0),
        "risk_count": int(latest.get("risk_count") or 0),
        "candidate_status_counts": latest.get("candidate_status_counts", {}),
        "sqlite_exists": bool(latest.get("sqlite_exists")),
        "export_directory_exists": bool(latest.get("export_directory_exists")),
        "path_fields_returned": False,
        "read_shape": latest.get("read_shape", {}),
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
        item["risk_tags_safe"] = [redact_visible_text(tag) for tag in item["risk_tags"]]
        for field in ["module_name", "title", "summary"]:
            item[field] = local_ui_display_text(item.get(field))
            item[f"{field}_safe"] = redact_visible_text(item.get(field))
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
        title = local_ui_display_text(item.get("title"))
        summary = local_ui_display_text(item.get("summary") or item.get("title") or "")
        raw_group_label = (
            item.get("group_name")
            or item.get("session_display_name")
            or item.get("session_name")
        )
        group_fields = (
            local_group_display_fields(raw_group_label, source="candidate_item")
            if clean_text(raw_group_label)
            else {
                "group_label": "",
                "group_label_safe": "",
                "group_label_status": "not_provided",
                "group_label_reason_code": "",
                "group_label_source_error_code": "",
            }
        )
        human_items.append(
            {
                "id": item_id,
                "display_id": local_ui_display_text(item.get("item_code")),
                "human_type": item_type_label(item.get("item_type")),
                "human_status": human_candidate_status(status, in_draft),
                "source_label": human_candidate_source_label(source),
                "action_label": candidate_action_label(source, status, in_draft),
                "title": title,
                "summary": summary,
                "summary_safe": redact_visible_text(summary),
                **group_fields,
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


def monitor_groups_payload(config: AppConfig) -> dict[str, Any]:
    groups = [monitor_group_public_payload(session) for session in config.sessions]
    customer_data = customer_options_with_source_payload(config)
    customer_options = customer_data["options"]
    field_options = monitor_group_field_options(config)
    return {
        "status": "ok",
        "title": "监控群",
        "count": len(groups),
        "active_count": len([group for group in groups if not group["archived"]]),
        "archived_count": len([group for group in groups if group["archived"]]),
        "daily_center_count": len(
            [group for group in groups if group["counts_in_daily_center"]]
        ),
        "customer_options": customer_options,
        "customer_options_count": len(customer_options),
        "customer_source_status": customer_data["source_status"],
        "customer_source_error_code": customer_data["source_error_code"],
        "customer_option_sources": customer_data["sources"],
        "field_options": field_options,
        "customer_name_options": field_options["customers"],
        "group_type_options": field_options["group_types"],
        "customer_stage_options": field_options["customer_stages"],
        "owner_options": field_options["owners"],
        "module_options": field_options["modules"],
        "option_source_summary": monitor_group_option_source_summary(
            config, customer_data
        ),
        "customer_match_contract": {
            "input": "group_name",
            "outputs": [
                "suggested_customer_name",
                "suggested_customer_id",
                "match_status",
                "reason_code",
            ],
            "manual_status": "needs_manual_selection",
        },
        "groups": groups,
        "actions": {
            "create": {"label": "新增监控群", "enabled": True},
            "edit": {"label": "保存群档案", "enabled": True},
            "disable": {"label": "停用监控", "enabled": True},
            "archive": {"label": "归档监控群", "enabled": True, "available": True},
            "delete": {
                "label": "删除本地监控群配置",
                "enabled": True,
                "available": True,
                "requires_confirmation": True,
            },
        },
        "save_contract": {
            "payload_fields": [
                "group_name",
                "customer_name",
                "customer_id",
                "group_type",
                "customer_stage",
                "owner_names",
                "common_contacts",
                "internal_people",
            ],
            "readback_fields": [
                "group_id",
                "customer_name",
                "customer_id",
                "group_type",
                "customer_stage",
                "owner_label",
            ],
        },
        "safety": {
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        },
    }


def monitor_group_customer_suggestion_payload(
    config: AppConfig,
    group_name: str,
    *,
    strawberry_loader: Callable[[], list[Any]] | None = None,
) -> dict[str, Any]:
    customer_data = customer_options_with_source_payload(
        config, strawberry_loader=strawberry_loader
    )
    customer_options = customer_data["options"]
    group_meta = local_group_display_meta(group_name, source="suggestion_query")
    suggestion = customer_suggestion_from_options(
        group_meta["value"] if group_meta["status"] == "resolved" else "",
        customer_options,
    )
    return {
        "status": "ok",
        "query_configured": bool(clean_text(group_name)),
        "query_display_status": group_meta["status"],
        "query_reason_code": group_meta["reason_code"],
        "customer_options_count": len(customer_options),
        "customer_source_status": customer_data["source_status"],
        "customer_source_error_code": customer_data["source_error_code"],
        "customer_option_sources": customer_data["sources"],
        "suggestion": suggestion,
        "suggested_customer_name": suggestion["suggested_customer_name"],
        "suggested_customer_id": suggestion["suggested_customer_id"],
        "match_status": suggestion["match_status"],
        "reason_code": suggestion["reason_code"],
        "safety": {
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "no_real_read_executed": True,
        },
    }


def customer_options_api_payload(
    config: AppConfig,
    *,
    strawberry_loader: Callable[[], list[Any]] | None = None,
) -> dict[str, Any]:
    customer_data = customer_options_with_source_payload(
        config, strawberry_loader=strawberry_loader
    )
    options = customer_data["options"]
    return {
        "status": "ok",
        "count": len(options),
        "customer_options_count": len(options),
        "source_status": customer_data["source_status"],
        "source_error_code": customer_data["source_error_code"],
        "sources": customer_data["sources"],
        "options": options,
        "customer_options": options,
        "source_label": "本地配置客户 / 草莓客户系统只读客户源",
        "safety": {
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "no_real_read_executed": True,
        },
    }


def monitor_group_detail_payload(
    config: AppConfig, group_id: str, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "group": {}}
    member_options = monitor_group_member_options(conn, session, config)
    field_options = monitor_group_field_options(config)
    group_meta = local_group_display_meta(session.display_name)
    return {
        "status": "ok",
        "group": monitor_group_public_payload(
            session, detail=True, member_options=member_options
        ),
        "field_options": field_options,
        "customer_options": customer_options_payload(config),
        "customer_name_options": field_options["customers"],
        "group_type_options": field_options["group_types"],
        "customer_stage_options": field_options["customer_stages"],
        "owner_options": field_options["owners"],
        "module_options": field_options["modules"],
        "customer_suggestion": customer_suggestion_payload(
            group_meta["value"] if group_meta["status"] == "resolved" else "",
            config,
        ),
        "member_options": member_options,
        "member_name_options": member_options["names"],
        "safety": {
            "save_triggers_collection": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        },
    }


def refresh_monitor_group_members_payload(
    config: AppConfig,
    group_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "member_options": empty_monitor_group_member_options()}
    member_options = monitor_group_member_options(conn, session, config)
    count = int(member_options["count"])
    return {
        "status": "refreshed" if count else "empty",
        "scope": member_options["scope"],
        "refresh_status": member_options["refresh_status"],
        "refresh_label": member_options["refresh_label"],
        "member_count": count,
        "available_count": int(member_options["available_count"]),
        "appeared_count": int(member_options["appeared_count"]),
        "roster_count": int(member_options["roster_count"]),
        "expected_count": member_options["expected_count"],
        "roster_status": member_options["roster_status"],
        "roster_status_label": member_options["roster_status_label"],
        "member_options": member_options,
        "member_name_options": member_options["names"],
        "full_sync_available": bool(member_options["full_sync_available"]),
        "full_sync_requires_authorization": bool(
            member_options["full_sync_requires_authorization"]
        ),
        "full_sync_status_label": member_options["full_sync_status_label"],
        "sync_action_label": member_options["sync_action_label"],
        "safety": {
            "save_triggers_collection": False,
            "real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "no_real_read_executed": True,
        },
    }


def sync_monitor_group_roster_payload(
    config: AppConfig,
    group_id: str,
    payload: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    *,
    runner: Any | None = None,
) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "member_options": empty_monitor_group_member_options()}
    body = payload or {}
    appeared_options = monitor_group_member_options(conn, session, config)
    appeared_summary = monitor_group_member_options_summary(appeared_options)
    authorized = parse_bool(body.get("authorize_full_roster_sync"), False)
    if not authorized:
        return {
            "status": "authorization_required",
            "scope": appeared_options["scope"],
            "member_options": appeared_summary,
            "available_count": int(appeared_options["available_count"]),
            "appeared_count": int(appeared_options["appeared_count"]),
            "roster_count": 0,
            "expected_count": None,
            "full_sync_available": bool(appeared_options["full_sync_available"]),
            "full_sync_requires_authorization": True,
            "roster_status": ROSTER_AUTH_REQUIRED_STATUS,
            "roster_status_label": ROSTER_AUTH_REQUIRED_LABEL,
            "sync_action_label": appeared_options["sync_action_label"],
            "safety": {
                "save_triggers_collection": False,
                "real_read_enabled": bool(config.wx_cli.real_read_enabled),
                "no_message_read_executed": True,
                "no_roster_read_executed": True,
            },
        }
    try:
        roster_members = fetch_group_roster_members(
            config,
            session,
            authorized=True,
            runner=runner,
        )
    except WxCliUnavailable as exc:
        return {
            "status": "blocked",
            "error_code": exc.code,
            "scope": appeared_options["scope"],
            "member_options": appeared_summary,
            "available_count": int(appeared_options["available_count"]),
            "appeared_count": int(appeared_options["appeared_count"]),
            "roster_count": 0,
            "expected_count": None,
            "full_sync_available": bool(appeared_options["full_sync_available"]),
            "full_sync_requires_authorization": bool(
                appeared_options["full_sync_requires_authorization"]
            ),
            "roster_status": exc.code,
            "roster_status_label": clean_text(exc.message) or ROSTER_UNAVAILABLE_LABEL,
            "sync_action_label": appeared_options["sync_action_label"],
            "safety": {
                "save_triggers_collection": False,
                "real_read_enabled": bool(config.wx_cli.real_read_enabled),
                "no_message_read_executed": True,
                "no_roster_read_executed": False,
            },
        }
    roster_names = unique_safe_member_names(
        [member.display_name for member in roster_members]
    )
    session.roster_member_names = unique_safe_member_names_for_session(
        roster_names, session
    )
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    member_options = monitor_group_member_option_payload(
        appeared_options["appeared_members"],
        session=session,
        roster_names=session.roster_member_names,
        roster_capability=roster_sync_capability_payload(config),
    )
    return {
        "status": "synced" if roster_names else "empty_roster",
        "scope": member_options["scope"],
        "member_options": member_options,
        "member_name_options": member_options["names"],
        "available_count": int(member_options["available_count"]),
        "appeared_count": int(member_options["appeared_count"]),
        "roster_count": int(member_options["roster_count"]),
        "expected_count": member_options["expected_count"],
        "full_sync_available": bool(member_options["full_sync_available"]),
        "full_sync_requires_authorization": bool(
            member_options["full_sync_requires_authorization"]
        ),
        "roster_status": member_options["roster_status"],
        "roster_status_label": member_options["roster_status_label"],
        "sync_action_label": member_options["sync_action_label"],
        "safety": {
            "save_triggers_collection": False,
            "real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "no_message_read_executed": True,
            "no_roster_read_executed": False,
        },
    }


def monitor_group_member_options_summary(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": options.get("scope"),
        "complete": bool(options.get("complete")),
        "status_label": options.get("status_label"),
        "source_label": options.get("source_label"),
        "count": int(options.get("count") or 0),
        "available_count": int(options.get("available_count") or 0),
        "appeared_count": int(options.get("appeared_count") or 0),
        "roster_count": int(options.get("roster_count") or 0),
        "expected_count": options.get("expected_count"),
        "refresh_status": options.get("refresh_status"),
        "roster_status": options.get("roster_status"),
        "roster_status_label": options.get("roster_status_label"),
        "full_sync_available": bool(options.get("full_sync_available")),
        "full_sync_requires_authorization": bool(
            options.get("full_sync_requires_authorization")
        ),
        "full_sync_status_label": options.get("full_sync_status_label"),
        "sync_action_label": options.get("sync_action_label"),
    }


def save_monitor_group_payload(
    config: AppConfig,
    payload: dict[str, Any],
    group_id: str | None = None,
    conn: sqlite3.Connection | None = None,
    *,
    roster_runner: Any | None = None,
) -> dict[str, Any]:
    session = find_monitor_group(config, group_id) if group_id else None
    if group_id and session is None:
        return {"status": "not_found", "group": {}}
    group_name = clean_text(payload.get("group_name")) or clean_text(
        payload.get("display_name")
    )
    if not group_name:
        return {
            "status": "blocked",
            "error_code": "monitor_group_name_required",
            "group": {},
        }
    group_meta = local_group_display_meta(group_name, source="user_input")
    display_name_for_save = group_meta["value"]
    if session is None:
        session = find_monitor_group_by_name(config, display_name_for_save)
    created = session is None
    if session is None:
        session = SessionConfig(
            external_id=local_monitor_external_id(group_name),
            display_name=display_name_for_save,
        )
        config.sessions.append(session)

    customer_options = customer_options_payload(config)
    customer_suggestion = customer_suggestion_from_options(
        display_name_for_save if group_meta["status"] == "resolved" else "",
        customer_options,
    )
    selected_customer = resolve_customer_selection(payload, customer_options)
    customer_name = selected_customer["customer_name"] or clean_text(
        payload.get("customer_name")
    )
    if not customer_name and customer_suggestion["match_status"] == "matched":
        customer_name = customer_suggestion["suggested_customer_name"]

    session.display_name = display_name_for_save
    session.display_name_status = group_meta["status"]
    session.display_name_source = group_meta["source"]
    session.display_name_reason_code = group_meta["reason_code"]
    session.customer_name = customer_name
    session.channel_name = clean_text(payload.get("channel_name"))
    session.module_name = clean_text(payload.get("module_name"))
    owner_names = clean_text_list(payload.get("owner_names", payload.get("owner_name")))
    session.owner_names = owner_names
    session.owner_name = owner_names[0] if owner_names else clean_text(payload.get("owner_name"))
    session.customer_stage = clean_text(payload.get("customer_stage"))
    session.group_type = clean_text(payload.get("group_type")) or "测试群"
    session.common_contacts = clean_text_list(payload.get("common_contacts"))
    session.reply_notes = clean_text(payload.get("reply_notes"))
    session.enabled = parse_bool(payload.get("enabled"), True)
    session.is_whitelisted = True
    session.verification_status = safe_verification_status(
        payload.get("verification_status")
    )
    session.daily_monitor_enabled = parse_bool(
        payload.get("daily_monitor_enabled"), True
    )
    session.include_in_daily = parse_bool(payload.get("include_in_daily"), False)
    session.trial_scope = clean_text(payload.get("trial_scope")) or "最近50条"
    session.internal_people = clean_text_list(payload.get("internal_people"))
    session.archived = parse_bool(payload.get("archived"), bool(getattr(session, "archived", False)))
    if session.archived:
        session.enabled = False
        session.daily_monitor_enabled = False
        session.include_in_daily = False
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    initial_roster_sync: dict[str, Any] | None = None
    if created:
        initial_roster_sync_result = sync_monitor_group_roster_payload(
            config,
            monitor_group_public_id(session),
            {
                "authorize_full_roster_sync": parse_bool(
                    payload.get("authorize_full_roster_sync_on_create"), False
                )
            },
            conn,
            runner=roster_runner,
        )
        initial_roster_sync = roster_sync_result_summary(initial_roster_sync_result)
    member_options = monitor_group_member_options(conn, session, config)
    result = {
        "status": "saved",
        "group": monitor_group_public_payload(
            session, detail=True, member_options=member_options
        ),
        "member_options": member_options,
        "member_name_options": member_options["names"],
        "customer_suggestion": customer_suggestion,
        "customer_options_count": len(customer_options),
        "real_read_enabled": False,
        "save_triggers_collection": False,
    }
    if initial_roster_sync is not None:
        result["initial_roster_sync"] = initial_roster_sync
    return result


def roster_sync_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    options = result.get("member_options")
    return {
        "status": result.get("status"),
        "error_code": result.get("error_code", ""),
        "scope": result.get("scope"),
        "complete": bool(options.get("complete")) if isinstance(options, dict) else False,
        "available_count": int(result.get("available_count") or 0),
        "appeared_count": int(result.get("appeared_count") or 0),
        "roster_count": int(result.get("roster_count") or 0),
        "expected_count": result.get("expected_count"),
        "full_sync_available": bool(result.get("full_sync_available")),
        "full_sync_requires_authorization": bool(
            result.get("full_sync_requires_authorization")
        ),
        "roster_status": result.get("roster_status"),
        "roster_status_label": result.get("roster_status_label"),
        "sync_action_label": result.get("sync_action_label"),
        "safety": result.get("safety", {}),
    }


def disable_monitor_group_payload(config: AppConfig, group_id: str) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "group": {}}
    session.enabled = False
    session.daily_monitor_enabled = False
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": "disabled",
        "group": monitor_group_public_payload(session, detail=True),
        "real_read_enabled": False,
        "save_triggers_collection": False,
    }


def archive_monitor_group_payload(config: AppConfig, group_id: str) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "group": {}}
    session.archived = True
    session.enabled = False
    session.daily_monitor_enabled = False
    session.include_in_daily = False
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": "archived",
        "group": monitor_group_public_payload(session, detail=True),
        "counts": monitor_group_collection_summary(config),
        "real_read_enabled": False,
        "save_triggers_collection": False,
        "safety": monitor_group_mutation_safety(config),
    }


def delete_monitor_group_payload(
    config: AppConfig, group_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    session = find_monitor_group(config, group_id)
    if session is None:
        return {"status": "not_found", "group": {}}
    confirmed = parse_bool(
        payload.get("confirm_delete", payload.get("confirmed")), False
    )
    if not confirmed:
        return {
            "status": "confirmation_required",
            "requires_confirmation": True,
            "group_id": group_id,
            "delete_label": "再次确认后删除本地监控群配置",
            "deleted": False,
            "counts": monitor_group_collection_summary(config),
            "safety": monitor_group_mutation_safety(config),
        }
    config.sessions = [
        item for item in config.sessions if monitor_group_public_id(item) != group_id
    ]
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": "deleted",
        "requires_confirmation": False,
        "deleted": True,
        "deleted_group_id": group_id,
        "counts": monitor_group_collection_summary(config),
        "real_read_enabled": False,
        "save_triggers_collection": False,
        "safety": monitor_group_mutation_safety(config),
    }


def monitor_group_collection_summary(config: AppConfig) -> dict[str, int]:
    return {
        "total_count": len(config.sessions),
        "active_count": len(
            [session for session in config.sessions if not bool(getattr(session, "archived", False))]
        ),
        "archived_count": len(
            [session for session in config.sessions if bool(getattr(session, "archived", False))]
        ),
        "daily_center_count": daily_center_monitor_group_count(config),
    }


def monitor_group_mutation_safety(config: AppConfig) -> dict[str, Any]:
    return {
        "save_triggers_collection": False,
        "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        "real_read_enabled": bool(config.wx_cli.real_read_enabled),
        "external_system_write": False,
        "formal_write_enabled": False,
        "local_config_only": True,
    }


def monitor_group_public_payload(
    session: SessionConfig,
    *,
    detail: bool = False,
    member_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verification = safe_verification_status(session.verification_status)
    counts = monitor_group_counts_in_daily_center(session)
    archived = bool(getattr(session, "archived", False))
    group_meta = local_group_display_meta(
        session.display_name,
        source=clean_text(getattr(session, "display_name_source", ""))
        or "config_display_name",
    )
    group_name = group_meta["value"]
    customer_name = local_ui_display_text(session.customer_name)
    group_type = local_ui_display_text(session.group_type)
    module_name = local_ui_display_text(session.module_name)
    customer_stage = local_ui_display_text(session.customer_stage)
    owner_label = local_ui_display_text(primary_owner_name(session)) or "待指定负责人"
    payload: dict[str, Any] = {
        "group_id": monitor_group_public_id(session),
        "display_name": group_name,
        "display_name_safe": redact_visible_text(group_name),
        "display_name_status": group_meta["status"],
        "display_name_source": group_meta["source"],
        "display_name_reason_code": group_meta["reason_code"],
        "display_name_source_error_code": group_meta["source_error_code"],
        "group_name": group_name,
        "group_name_safe": redact_visible_text(group_name),
        "group_name_status": group_meta["status"],
        "group_name_reason_code": group_meta["reason_code"],
        "group_name_source_error_code": group_meta["source_error_code"],
        "redacted_group_label": redact_visible_text(group_name),
        "archived": archived,
        "enabled": bool(session.enabled),
        "enabled_label": "启用" if session.enabled else "停用",
        "status_label": monitor_group_status_label(session),
        "verification_status": verification,
        "verification_label": monitor_group_verification_label(verification),
        "daily_monitor_enabled": bool(session.daily_monitor_enabled),
        "daily_monitor_label": (
            "每日监控" if session.daily_monitor_enabled else "不做每日监控"
        ),
        "include_in_daily": bool(session.include_in_daily),
        "include_daily_label": "纳入日报" if session.include_in_daily else "不纳入日报",
        "counts_in_daily_center": counts,
        "customer_name": customer_name,
        "customer_name_safe": redact_visible_text(customer_name),
        "customer_id": local_customer_id(session.customer_name),
        "customer_match": customer_suggestion_payload(
            group_name if group_meta["status"] == "resolved" else "",
            None,
            [session.customer_name],
        ),
        "group_type": group_type,
        "group_type_safe": redact_visible_text(group_type),
        "module_name": module_name,
        "module_name_safe": redact_visible_text(module_name),
        "customer_stage": customer_stage,
        "customer_stage_safe": redact_visible_text(customer_stage),
        "owner_label": owner_label,
        "owner_label_safe": redact_visible_text(owner_label),
        "configuration_status_label": monitor_group_configuration_label(session),
        "can_edit": True,
        "can_disable": bool(session.enabled and not archived),
        "can_archive": not archived,
        "can_delete": True,
        "delete_requires_confirmation": True,
        "archive_action_label": "归档监控群",
        "delete_action_label": "删除本地监控群配置",
        "can_trial_read": bool(session.enabled and not archived),
    }
    if detail:
        channel_name = local_ui_display_text(session.channel_name)
        trial_scope = local_ui_display_text(session.trial_scope) or "最近50条"
        reply_notes = local_ui_display_text(session.reply_notes)
        owner_names = local_ui_display_list(normalized_owner_names(session))
        common_contacts = local_ui_display_list(list(session.common_contacts))
        internal_people = local_ui_display_list(list(session.internal_people))
        payload.update(
            {
                "customer_name": customer_name,
                "customer_name_safe": redact_visible_text(customer_name),
                "customer_id": local_customer_id(session.customer_name),
                "channel_name": channel_name,
                "channel_name_safe": redact_visible_text(channel_name),
                "owner_name": primary_owner_name(session),
                "owner_name_safe": redact_visible_text(primary_owner_name(session)),
                "owner_names": owner_names,
                "owner_names_safe": [redact_visible_text(person) for person in owner_names],
                "common_contacts": common_contacts,
                "common_contacts_safe": [
                    redact_visible_text(contact) for contact in common_contacts
                ],
                "internal_people": internal_people,
                "internal_people_safe": [
                    redact_visible_text(person) for person in internal_people
                ],
                "trial_scope": trial_scope,
                "trial_scope_safe": redact_visible_text(trial_scope),
                "reply_notes": reply_notes,
                "reply_notes_safe": redact_visible_text(reply_notes),
                "member_options": member_options or empty_monitor_group_member_options(),
                "member_name_options": (member_options or empty_monitor_group_member_options())["names"],
            }
        )
    return payload


def monitor_group_field_options(config: AppConfig) -> dict[str, Any]:
    customer_options = customer_options_payload(config)
    owners = sorted(
        {person.person_name for person in config.internal_people if person.person_name}
        | {session.owner_name for session in config.sessions if session.owner_name}
        | {
            owner
            for session in config.sessions
            for owner in normalized_owner_names(session)
        }
    )
    common_people = sorted(
        set(owners)
        | {
            contact
            for session in config.sessions
            for contact in session.common_contacts
            if contact
        }
        | {
            person
            for session in config.sessions
            for person in session.internal_people
            if person
        }
    )
    return {
        "group_types": ["测试群", "客户群", "渠道群", "内部群"],
        "customers": [option["customer_name"] for option in customer_options],
        "customer_options": customer_options,
        "modules": sorted(
            {session.module_name for session in config.sessions if session.module_name}
            | {"售后", "订单", "电商设计", "渠道"}
        ),
        "customer_stages": ["试读验证", "试用期", "交付期", "合作期", "已收口"],
        "owners": owners,
        "owner_name_options": owners,
        "common_contact_options": common_people,
        "internal_people_options": common_people,
        "trial_scopes": ["最近50条", "指定时间段"],
        "verification_statuses": ["待验证", "已验证"],
    }


def monitor_group_option_source_summary(
    config: AppConfig, customer_data: dict[str, Any]
) -> dict[str, Any]:
    field_options = monitor_group_field_options(config)
    return {
        "customer_options_count": len(customer_data.get("options", [])),
        "customer_source_status": customer_data.get("source_status"),
        "group_type_count": len(field_options["group_types"]),
        "customer_stage_count": len(field_options["customer_stages"]),
        "owner_count": len(field_options["owners"]),
        "module_count": len(field_options["modules"]),
        "source_label": "本地配置 / 已保存群档案 / 我方人员库 / 客户系统只读源",
    }


APPEARED_MEMBER_SCOPE = "appeared_members"
ROSTER_MEMBER_SCOPE = "roster_members"
APPEARED_MEMBER_SOURCE_LABEL = "本地已出现成员（不是全员名单）"
ROSTER_MEMBER_SOURCE_LABEL = "微信群全员名单"
ROSTER_UNAVAILABLE_STATUS = "need_wx_cli_roster_capability"
ROSTER_AUTH_REQUIRED_STATUS = "authorization_required"
ROSTER_SYNCED_STATUS = "synced"
ROSTER_UNAVAILABLE_LABEL = "完整群成员名单需要真实 wx-cli members 能力或 WeChat 元数据只读接口。"
ROSTER_AUTH_REQUIRED_LABEL = "已定位到微信群全员名单能力；需用户点击同步并授权后才读取完整名单。"
ROSTER_SYNCED_LABEL = "已同步微信群全员名单；仅返回昵称级显示文本。"
MONITOR_GROUP_MEMBER_ROLE_LABELS = {
    "group_owner": "群负责人",
    "common_contact": "常用联系人",
    "internal_person": "我方人员",
}
MONITOR_GROUP_MEMBER_ROLE_TARGETS = {
    "group_owner": "owner_names",
    "common_contact": "common_contacts",
    "internal_person": "internal_people",
}


def empty_monitor_group_member_options() -> dict[str, Any]:
    return monitor_group_member_option_payload([])


def monitor_group_member_option_payload(
    appeared_names: list[str],
    session: SessionConfig | None = None,
    *,
    roster_names: list[str] | None = None,
    roster_capability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_appeared_names = (
        unique_safe_member_names_for_session(appeared_names, session)
        if session is not None
        else unique_safe_member_names(appeared_names)
    )
    safe_roster_names = (
        unique_safe_member_names_for_session(roster_names or [], session)
        if session is not None
        else unique_safe_member_names(roster_names or [])
    )
    has_roster = bool(safe_roster_names)
    names = safe_roster_names if has_roster else safe_appeared_names
    available_count = len(names)
    appeared_count = len(safe_appeared_names)
    roster_count = len(safe_roster_names)
    capability = roster_capability or roster_sync_capability_payload(None)
    roster_status = (
        ROSTER_SYNCED_STATUS if has_roster else str(capability["roster_status"])
    )
    roster_status_label = (
        ROSTER_SYNCED_LABEL if has_roster else str(capability["roster_status_label"])
    )
    full_sync_available = bool(capability["full_sync_available"])
    full_sync_requires_authorization = bool(
        capability["full_sync_requires_authorization"]
    )
    status_label = (
        ROSTER_SYNCED_LABEL
        if has_roster
        else (
            "当前只列出本地已出现 / 已保存成员，不是微信群全员名单；"
            f"{roster_status_label}"
            if names
            else f"暂无本地已出现成员；{roster_status_label}"
        )
    )
    refresh_status = "local_rebuilt" if names else "empty_local_sources"
    role_sets = monitor_group_member_role_sets(session)
    items = [
        monitor_group_member_option_item(name, role_sets)
        for name in names
    ]
    return {
        "scope": ROSTER_MEMBER_SCOPE if has_roster else APPEARED_MEMBER_SCOPE,
        "complete": has_roster,
        "status_label": status_label,
        "source_label": (
            ROSTER_MEMBER_SOURCE_LABEL if has_roster else APPEARED_MEMBER_SOURCE_LABEL
        ),
        "count": available_count,
        "available_count": available_count,
        "appeared_count": appeared_count,
        "roster_count": roster_count,
        "expected_count": roster_count if has_roster else None,
        "names": names,
        "items": items,
        "role_labels": MONITOR_GROUP_MEMBER_ROLE_LABELS,
        "role_field_targets": MONITOR_GROUP_MEMBER_ROLE_TARGETS,
        "appeared_members": safe_appeared_names,
        "roster_members": safe_roster_names,
        "full_members": safe_roster_names,
        "refresh_available": True,
        "refresh_label": "刷新本地已出现成员",
        "refresh_status": refresh_status,
        "roster_refresh_available": full_sync_available,
        "roster_status": roster_status,
        "roster_status_label": roster_status_label,
        "full_sync_available": full_sync_available,
        "full_sync_requires_authorization": full_sync_requires_authorization,
        "full_sync_status_label": roster_status_label,
        "sync_action_label": (
            "重新同步微信群全员名单" if has_roster else "同步微信群全员名单"
        ),
    }


def monitor_group_member_options(
    conn: sqlite3.Connection | None,
    session: SessionConfig,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    names: list[str] = []
    if conn is not None:
        names.extend(local_message_member_names(conn, session))
    if config is not None:
        names.extend(latest_trial_member_names(config, session))
    names.extend(normalized_owner_names(session))
    names.extend(session.common_contacts)
    names.extend(session.internal_people)
    roster_names = list(getattr(session, "roster_member_names", []) or [])
    safe_names = unique_safe_member_names_for_session(names, session)
    return monitor_group_member_option_payload(
        safe_names,
        session=session,
        roster_names=roster_names,
        roster_capability=roster_sync_capability_payload(config),
    )


def roster_sync_capability_payload(config: AppConfig | None) -> dict[str, Any]:
    if config is None:
        return {
            "full_sync_available": False,
            "full_sync_requires_authorization": False,
            "roster_status": ROSTER_UNAVAILABLE_STATUS,
            "roster_status_label": ROSTER_UNAVAILABLE_LABEL,
        }
    if config.wx_cli.mode != "real":
        return {
            "full_sync_available": False,
            "full_sync_requires_authorization": False,
            "roster_status": "real_mode_required",
            "roster_status_label": "完整群成员同步需要真实 wx-cli 模式；当前不会执行。",
        }
    readiness = wx_cli_readiness(config)
    if readiness["status"] != "ok":
        return {
            "full_sync_available": False,
            "full_sync_requires_authorization": False,
            "roster_status": readiness["status"],
            "roster_status_label": ROSTER_UNAVAILABLE_LABEL,
        }
    return {
        "full_sync_available": True,
        "full_sync_requires_authorization": True,
        "roster_status": ROSTER_AUTH_REQUIRED_STATUS,
        "roster_status_label": ROSTER_AUTH_REQUIRED_LABEL,
    }


def unique_safe_member_names_for_session(
    values: list[Any],
    session: SessionConfig,
) -> list[str]:
    excluded = monitor_group_member_excluded_names(session)
    return [
        name
        for name in unique_safe_member_names(values)
        if name not in excluded
    ]


def monitor_group_member_excluded_names(session: SessionConfig) -> set[str]:
    return set(
        unique_safe_member_names(
            [
                session.display_name,
                session.external_id,
                session.channel_name,
            ]
        )
    )


def monitor_group_member_role_sets(
    session: SessionConfig | None,
) -> dict[str, set[str]]:
    if session is None:
        return {role: set() for role in MONITOR_GROUP_MEMBER_ROLE_LABELS}
    return {
        "group_owner": set(unique_safe_member_names(normalized_owner_names(session))),
        "common_contact": set(unique_safe_member_names(session.common_contacts)),
        "internal_person": set(unique_safe_member_names(session.internal_people)),
    }


def monitor_group_member_option_item(
    name: str,
    role_sets: dict[str, set[str]],
) -> dict[str, Any]:
    selected_roles = [
        role
        for role in MONITOR_GROUP_MEMBER_ROLE_LABELS
        if name in role_sets.get(role, set())
    ]
    role_flags = {
        role: role in selected_roles
        for role in MONITOR_GROUP_MEMBER_ROLE_LABELS
    }
    return {
        "value": name,
        "label": name,
        "selected_roles": selected_roles,
        "selected_role_labels": [
            MONITOR_GROUP_MEMBER_ROLE_LABELS[role] for role in selected_roles
        ],
        "role_flags": role_flags,
    }


def local_message_member_names(
    conn: sqlite3.Connection, session: SessionConfig
) -> list[str]:
    names = exact_session_member_names(conn, session)
    if names:
        return names
    return single_session_member_names(conn)


def latest_trial_member_names(config: AppConfig, session: SessionConfig) -> list[str]:
    latest_db = latest_real_trial_db(Path(config.root) / "data")
    if latest_db is None:
        return []
    try:
        uri = f"file:{latest_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            names = exact_session_member_names(conn, session)
            if names:
                return names
            return single_session_member_names(conn)
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def exact_session_member_names(
    conn: sqlite3.Connection, session: SessionConfig
) -> list[str]:
    try:
        rows = conn.execute(
            """
            select distinct rm.sender_display_name
            from raw_messages rm
            join sessions s on s.id = rm.session_id
            where s.external_id = ? or s.display_name = ?
            order by rm.sender_display_name
            """,
            (session.external_id, session.display_name),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row["sender_display_name"] or "") for row in rows]


def single_session_member_names(conn: sqlite3.Connection) -> list[str]:
    try:
        session_count = conn.execute(
            """
            select count(distinct session_id) as count
            from raw_messages
            """
        ).fetchone()["count"]
        if int(session_count or 0) != 1:
            return []
        rows = conn.execute(
            """
            select distinct sender_display_name
            from raw_messages
            order by sender_display_name
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row["sender_display_name"] or "") for row in rows]


def normalized_owner_names(session: SessionConfig) -> list[str]:
    names = list(getattr(session, "owner_names", []) or [])
    if session.owner_name:
        names.insert(0, session.owner_name)
    return unique_clean_text(names)


def primary_owner_name(session: SessionConfig) -> str:
    names = normalized_owner_names(session)
    return names[0] if names else ""


def unique_safe_member_names(values: list[Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = safe_member_display_name(value)
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def safe_member_display_name(value: Any) -> str:
    display = safe_sender_display(value)
    if not display or display == "未解析微信名":
        return ""
    redacted = redact_visible_text(display)
    if "[敏感信息已脱敏]" in redacted or "[路径已脱敏]" in redacted:
        return ""
    lowered = redacted.lower()
    if any(token in lowered for token in ["wxid", "key", "salt", "daemon"]):
        return ""
    return redacted


def unique_clean_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def find_monitor_group(config: AppConfig, group_id: str | None) -> SessionConfig | None:
    if not group_id:
        return None
    return next(
        (
            session
            for session in config.sessions
            if monitor_group_public_id(session) == group_id
        ),
        None,
    )


def find_monitor_group_by_name(
    config: AppConfig, group_name: str
) -> SessionConfig | None:
    return next(
        (
            session
            for session in config.sessions
            if clean_text(session.display_name) == group_name
        ),
        None,
    )


def monitor_group_public_id(session: SessionConfig) -> str:
    seed = clean_text(session.external_id) or clean_text(session.display_name)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"mg-{digest}"


def local_monitor_external_id(group_name: str) -> str:
    digest = hashlib.sha256(group_name.encode("utf-8")).hexdigest()[:12]
    return f"local-monitor-{digest}"


def local_customer_id(customer_name: Any) -> str:
    name = safe_customer_name(customer_name)
    if not name:
        return ""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"customer-{digest}"


def safe_customer_name(value: Any) -> str:
    name = redact_visible_text(clean_text(value))
    if not name or "[敏感信息已脱敏]" in name or "[路径已脱敏]" in name:
        return ""
    lowered = name.lower()
    if any(token in lowered for token in ["wxid", "key", "salt", "daemon"]):
        return ""
    return name


STRAWBERRY_CUSTOMER_PROJECT_ROOT = Path.home() / "Desktop" / "主业--草莓客户管理系统"
STRAWBERRY_CUSTOMER_SOURCE = "strawberry_customer_system"
LOCAL_CUSTOMER_SOURCE = "local_config"


def customer_options_with_source_payload(
    config: AppConfig | None,
    *,
    strawberry_loader: Callable[[], list[Any]] | None = None,
) -> dict[str, Any]:
    local_options = local_customer_options_payload(config)
    if strawberry_loader is None and not default_strawberry_source_enabled(config):
        strawberry_source = strawberry_customer_source_error("source_disabled_for_test_root")
    else:
        strawberry_source = strawberry_customer_source_payload(strawberry_loader)
    options = merge_customer_options(local_options, strawberry_source["options"])
    source_summary = [
        {
            "source": LOCAL_CUSTOMER_SOURCE,
            "source_label": "本项目本地配置",
            "status": "ok",
            "count": len(local_options),
            "error_code": "",
        },
        {
            "source": STRAWBERRY_CUSTOMER_SOURCE,
            "source_label": "草莓客户系统只读客户源",
            "status": strawberry_source["status"],
            "count": strawberry_source["count"],
            "error_code": strawberry_source["error_code"],
        },
    ]
    source_status = (
        "ok" if strawberry_source["status"] == "ok" else "partial"
    )
    return {
        "options": options,
        "count": len(options),
        "customer_options_count": len(options),
        "source_status": source_status,
        "source_error_code": strawberry_source["error_code"],
        "sources": source_summary,
    }


def default_strawberry_source_enabled(config: AppConfig | None) -> bool:
    if config is None:
        return False
    try:
        return Path(config.root).resolve() == Path.cwd().resolve()
    except OSError:
        return False


def customer_options_payload(
    config: AppConfig | None,
    *,
    strawberry_loader: Callable[[], list[Any]] | None = None,
) -> list[dict[str, Any]]:
    return customer_options_with_source_payload(
        config, strawberry_loader=strawberry_loader
    )["options"]


def local_customer_options_payload(config: AppConfig | None) -> list[dict[str, Any]]:
    if config is None:
        return []
    counts: dict[str, int] = {}
    first_seen_order: list[str] = []
    for session in config.sessions:
        customer_name = safe_customer_name(session.customer_name)
        if not customer_name:
            continue
        if customer_name not in counts:
            first_seen_order.append(customer_name)
        counts[customer_name] = counts.get(customer_name, 0) + 1
    return [
        {
            "customer_id": local_customer_id(customer_name),
            "customer_name": customer_name,
            "label": customer_name,
            "source_label": "本地配置客户",
            "source_count": counts[customer_name],
            "source": LOCAL_CUSTOMER_SOURCE,
        }
        for customer_name in sorted(first_seen_order)
    ]


def strawberry_customer_source_payload(
    loader: Callable[[], list[Any]] | None = None,
) -> dict[str, Any]:
    try:
        records = loader() if loader is not None else load_strawberry_customer_records()
    except FileNotFoundError:
        return strawberry_customer_source_error("source_path_missing")
    except ModuleNotFoundError:
        return strawberry_customer_source_error("source_module_unavailable")
    except Exception:
        return strawberry_customer_source_error("source_read_failed")
    options = strawberry_customer_options_from_records(records)
    return {
        "status": "ok",
        "error_code": "",
        "count": len(options),
        "options": options,
    }


def strawberry_customer_source_error(error_code: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "error_code": error_code,
        "count": 0,
        "options": [],
    }


def load_strawberry_customer_records() -> list[Any]:
    source_dir = STRAWBERRY_CUSTOMER_PROJECT_ROOT / "src"
    if not source_dir.exists():
        raise FileNotFoundError("strawberry customer source missing")
    inserted = False
    source_text = str(source_dir)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
        inserted = True
    try:
        from strawberry_customer_management.markdown_store import MarkdownCustomerStore

        return MarkdownCustomerStore().list_customers()
    finally:
        if inserted:
            try:
                sys.path.remove(source_text)
            except ValueError:
                pass


def strawberry_customer_options_from_records(records: list[Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    first_seen_order: list[str] = []
    for record in records:
        name = safe_customer_name(customer_name_from_record(record))
        if not name:
            continue
        if name not in counts:
            first_seen_order.append(name)
        counts[name] = counts.get(name, 0) + 1
    return [
        {
            "customer_id": local_customer_id(customer_name),
            "customer_name": customer_name,
            "label": customer_name,
            "source_label": "草莓客户系统",
            "source_count": counts[customer_name],
            "source": STRAWBERRY_CUSTOMER_SOURCE,
        }
        for customer_name in sorted(first_seen_order)
    ]


def customer_name_from_record(record: Any) -> str:
    if isinstance(record, dict):
        return clean_text(record.get("name") or record.get("customer_name"))
    return clean_text(getattr(record, "name", record))


def merge_customer_options(
    local_options: list[dict[str, Any]],
    strawberry_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for option in [*local_options, *strawberry_options]:
        name = safe_customer_name(option.get("customer_name"))
        if not name:
            continue
        if name not in by_name:
            by_name[name] = {
                "customer_id": local_customer_id(name),
                "customer_name": name,
                "label": name,
                "source_label": clean_text(option.get("source_label")),
                "source_count": int(option.get("source_count") or 1),
                "sources": [clean_text(option.get("source")) or LOCAL_CUSTOMER_SOURCE],
            }
            order.append(name)
            continue
        existing = by_name[name]
        source = clean_text(option.get("source")) or LOCAL_CUSTOMER_SOURCE
        if source not in existing["sources"]:
            existing["sources"].append(source)
        existing["source_count"] = int(existing.get("source_count") or 0) + int(
            option.get("source_count") or 1
        )
        labels = [
            label
            for label in [
                clean_text(existing.get("source_label")),
                clean_text(option.get("source_label")),
            ]
            if label
        ]
        existing["source_label"] = " / ".join(dict.fromkeys(labels))
    return [by_name[name] for name in sorted(order)]


def resolve_customer_selection(
    payload: dict[str, Any], customer_options: list[dict[str, Any]]
) -> dict[str, str]:
    customer_name = safe_customer_name(payload.get("customer_name"))
    customer_id = clean_text(payload.get("customer_id"))
    if customer_name:
        return {"customer_name": customer_name, "customer_id": local_customer_id(customer_name)}
    if customer_id:
        for option in customer_options:
            if clean_text(option.get("customer_id")) == customer_id:
                return {
                    "customer_name": safe_customer_name(option.get("customer_name")),
                    "customer_id": customer_id,
                }
    return {"customer_name": "", "customer_id": ""}


def customer_suggestion_payload(
    group_name: Any,
    config: AppConfig | None = None,
    customer_names: list[Any] | None = None,
) -> dict[str, Any]:
    if customer_names is not None:
        options = [
            {
                "customer_id": local_customer_id(name),
                "customer_name": safe_customer_name(name),
                "label": safe_customer_name(name),
                "source_label": "已保存群客户",
                "source_count": 1,
            }
            for name in customer_names
            if safe_customer_name(name)
        ]
    else:
        options = customer_options_payload(config)
    return customer_suggestion_from_options(group_name, options)


def customer_suggestion_from_options(
    group_name: Any, customer_options: list[dict[str, Any]]
) -> dict[str, Any]:
    safe_group_name = safe_customer_name(group_name)
    base = {
        "suggested_customer_name": "",
        "suggested_customer_id": "",
        "match_status": "needs_manual_selection",
        "reason_code": "no_reliable_match",
        "customer_options_count": len(customer_options),
    }
    if not safe_group_name:
        base["reason_code"] = "empty_group_name"
        return base
    if not customer_options:
        base["reason_code"] = "no_customer_options"
        return base

    exact_matches: list[dict[str, Any]] = []
    substring_matches: list[dict[str, Any]] = []
    normalized_matches: list[dict[str, Any]] = []
    normalized_group = normalize_customer_match_text(safe_group_name)
    group_variants = customer_group_match_variants(safe_group_name)
    weak_suggestion: dict[str, Any] | None = None
    weak_score = 0.0
    for option in customer_options:
        customer_name = safe_customer_name(option.get("customer_name"))
        if not customer_name:
            continue
        normalized_customer = normalize_customer_match_text(customer_name)
        customer_variants = customer_name_match_variants(customer_name)
        if safe_group_name == customer_name or normalized_group == normalized_customer:
            exact_matches.append(option)
        elif len(customer_name) >= 2 and customer_name in safe_group_name:
            substring_matches.append(option)
        elif (
            len(normalized_customer) >= 2
            and normalized_customer
            and normalized_customer in normalized_group
        ):
            normalized_matches.append(option)
        elif customer_match_variants_overlap(group_variants, customer_variants):
            normalized_matches.append(option)
        else:
            score = customer_match_confidence(group_variants, customer_variants)
            if score > weak_score:
                weak_score = score
                weak_suggestion = option

    for reason, matches in [
        ("exact_match", exact_matches),
        ("substring_match", substring_matches),
        ("normalized_match", normalized_matches),
    ]:
        unique_matches = unique_customer_options(matches)
        if len(unique_matches) == 1:
            option = unique_matches[0]
            return {
                "suggested_customer_name": safe_customer_name(option.get("customer_name")),
                "suggested_customer_id": clean_text(option.get("customer_id")),
                "match_status": "matched",
                "reason_code": reason,
                "customer_options_count": len(customer_options),
            }
        if len(unique_matches) > 1:
            base["reason_code"] = "multiple_matches"
            return base
    if weak_suggestion and weak_score >= 0.45:
        base["suggested_customer_name"] = safe_customer_name(
            weak_suggestion.get("customer_name")
        )
        base["suggested_customer_id"] = clean_text(weak_suggestion.get("customer_id"))
        base["reason_code"] = "low_confidence_suggestion"
    return base


def unique_customer_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for option in options:
        customer_id = clean_text(option.get("customer_id"))
        customer_name = safe_customer_name(option.get("customer_name"))
        key = customer_id or customer_name
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(option)
    return result


def normalize_customer_match_text(value: Any) -> str:
    return "".join(ch.lower() for ch in clean_text(value) if ch.isalnum())


CUSTOMER_GROUP_NOISE_TERMS = [
    "客户群",
    "项目群",
    "售后群",
    "对接群",
    "交流群",
    "试读群",
    "监控群",
    "微信群",
    "工作群",
    "小红书",
    "抖音",
    "天猫",
    "淘宝",
    "京东",
    "拼多多",
    "视频号",
    "快手",
    "企微",
    "微信",
    "渠道",
    "平台",
    "群",
]
CUSTOMER_CONNECTOR_CHARS = ["x", "×", "&", "＋", "+", "和", "与"]


def customer_group_match_variants(value: Any) -> set[str]:
    variants = customer_name_match_variants(value)
    for variant in list(variants):
        without_noise = variant
        for term in CUSTOMER_GROUP_NOISE_TERMS:
            normalized_term = normalize_customer_match_text(term)
            if normalized_term:
                without_noise = without_noise.replace(normalized_term, "")
        if without_noise:
            variants.add(without_noise)
            variants.add(remove_customer_connectors(without_noise))
    return {variant for variant in variants if variant}


def customer_name_match_variants(value: Any) -> set[str]:
    base = normalize_customer_match_text(value)
    variants = {base, remove_customer_connectors(base)}
    return {variant for variant in variants if variant}


def remove_customer_connectors(value: str) -> str:
    result = clean_text(value)
    for connector in CUSTOMER_CONNECTOR_CHARS:
        result = result.replace(connector, "")
    return result


def customer_match_variants_overlap(
    group_variants: set[str], customer_variants: set[str]
) -> bool:
    for customer_variant in customer_variants:
        if len(customer_variant) < 2:
            continue
        for group_variant in group_variants:
            if (
                customer_variant == group_variant
                or customer_variant in group_variant
                or group_variant in customer_variant
                and len(group_variant) >= max(2, len(customer_variant) - 1)
            ):
                return True
    return False


def customer_match_confidence(
    group_variants: set[str], customer_variants: set[str]
) -> float:
    best = 0.0
    for customer_variant in customer_variants:
        if len(customer_variant) < 2:
            continue
        for group_variant in group_variants:
            common = longest_common_substring_length(group_variant, customer_variant)
            denominator = max(1, len(customer_variant))
            best = max(best, common / denominator)
    return best


def longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    best = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            length = previous[index - 1] + 1 if left_char == right_char else 0
            current.append(length)
            best = max(best, length)
        previous = current
    return best


def safe_verification_status(value: Any) -> str:
    status = clean_text(value)
    return status if status in {"pending_verification", "verified"} else "pending_verification"


def monitor_group_verification_label(status: str) -> str:
    return "已验证" if status == "verified" else "待验证"


def monitor_group_status_label(session: SessionConfig) -> str:
    if bool(getattr(session, "archived", False)):
        return "已归档"
    if not session.enabled:
        return "已停用"
    if safe_verification_status(session.verification_status) != "verified":
        return "待验证"
    return "监控中"


def monitor_group_counts_in_daily_center(session: SessionConfig) -> bool:
    return bool(
        not bool(getattr(session, "archived", False))
        and session.enabled
        and session.daily_monitor_enabled
        and session.include_in_daily
        and safe_verification_status(session.verification_status) == "verified"
    )


def daily_center_monitor_group_count(config: AppConfig) -> int:
    return len(
        [session for session in config.sessions if monitor_group_counts_in_daily_center(session)]
    )


def monitor_group_configuration_label(session: SessionConfig) -> str:
    if bool(getattr(session, "archived", False)):
        return "已归档"
    missing = []
    if not clean_text(session.customer_name or session.channel_name):
        missing.append("客户")
    if not clean_text(primary_owner_name(session)):
        missing.append("负责人")
    if not clean_text(session.module_name):
        missing.append("业务模块")
    if not session.include_in_daily:
        missing.append("日报")
    if not session.daily_monitor_enabled:
        missing.append("每日监控")
    if not missing:
        return "配置完整"
    return "待补：" + "、".join(missing)


def internal_people_payload(
    config: AppConfig, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    people = [internal_person_public_payload(person, config, conn) for person in config.internal_people]
    return {
        "status": "ok",
        "title": "我方人员",
        "count": len(people),
        "people": people,
        "field_contract": {
            "required": ["person_name"],
            "optional": ["wechat_display_name", "aliases", "role", "modules", "enabled", "notes"],
            "aliases_separator_label": "支持逗号、空格、换行分割",
        },
        "suggestion_contract": internal_people_suggestion_contract(),
        "save_readback_contract": {
            "save_endpoint": "/api/internal-people",
            "update_endpoint": "/api/internal-people/{person_id}",
            "disable_endpoint": "/api/internal-people/{person_id}/disable",
            "readback_endpoint": "/api/internal-people",
            "readback_fields": [
                "person_id",
                "person_name",
                "wechat_display_name",
                "aliases",
                "role",
                "modules",
                "enabled",
                "notes",
            ],
        },
        "suggestion_sources": internal_people_source_summary(config, conn),
        "downstream_status": internal_people_downstream_status(config, conn),
        "safety": internal_people_safety_payload(config),
    }


def internal_person_public_payload(
    person: PersonConfig,
    config: AppConfig,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    aliases = normalized_person_aliases(person)
    person_name = local_ui_display_text(person.person_name)
    wechat_display_name = local_ui_display_text(person.wechat_display_name)
    modules = [
        local_ui_display_text(module)
        for module in person.modules
        if local_ui_display_text(module)
    ]
    notes = local_ui_display_text(getattr(person, "notes", ""))
    return {
        "person_id": person_public_id(person),
        "person_name": person_name,
        "person_name_safe": redact_visible_text(person_name),
        "name": person_name,
        "name_safe": redact_visible_text(person_name),
        "wechat_display_name": wechat_display_name,
        "wechat_display_name_safe": redact_visible_text(wechat_display_name),
        "common_names": aliases,
        "common_names_safe": [redact_visible_text(alias) for alias in aliases],
        "aliases": aliases,
        "aliases_safe": [redact_visible_text(alias) for alias in aliases],
        "role": clean_text(person.role) or "我方人员",
        "modules": modules,
        "modules_safe": [redact_visible_text(module) for module in modules],
        "enabled": bool(person.enabled),
        "enabled_label": "启用" if person.enabled else "停用",
        "notes": notes,
        "notes_safe": redact_visible_text(notes),
        "initial_identity": "我方人员",
        "confidence": "已匹配" if aliases else "可能是",
        "requires_display_name": False,
        "impact": internal_person_impact_payload(config, conn, person),
    }


def internal_people_suggestions_payload(
    config: AppConfig, conn: sqlite3.Connection | None, payload: dict[str, Any]
) -> dict[str, Any]:
    query = clean_text(
        payload.get("display_name")
        or payload.get("name")
        or payload.get("wechat_display_name")
        or payload.get("query")
    )
    raw_wechat_id = clean_text(payload.get("wechat_id"))
    requires_display_name = bool(raw_wechat_id and not query)
    if requires_display_name:
        return {
            "status": "requires_display_name",
            "requires_display_name": True,
            "query_label": "",
            "count": 0,
            "suggestions": [],
            "suggestion_contract": internal_people_suggestion_contract(),
            "message": "只拿到内部标识，缺少可显示微信名；请补充微信显示名后再保存。",
            "source_summary": internal_people_source_summary(config, conn),
            "safety": internal_people_safety_payload(config),
        }
    display_query = local_ui_display_text(query)
    if not display_query:
        return {
            "status": "empty",
            "requires_display_name": False,
            "query_label": "",
            "count": 0,
            "suggestions": [],
            "suggestion_contract": internal_people_suggestion_contract(),
            "message": "请输入人员姓名或微信显示名。",
            "source_summary": internal_people_source_summary(config, conn),
            "safety": internal_people_safety_payload(config),
        }
    suggestions = build_internal_person_suggestions(config, conn, display_query)
    return {
        "status": "ok",
        "requires_display_name": False,
        "query_label": display_query,
        "query_label_safe": redact_visible_text(display_query),
        "count": len(suggestions),
        "suggestions": suggestions,
        "suggestion_contract": internal_people_suggestion_contract(),
        "source_summary": internal_people_source_summary(config, conn),
        "safety": internal_people_safety_payload(config),
    }


def save_internal_person_payload(
    config: AppConfig,
    conn: sqlite3.Connection | None,
    payload: dict[str, Any],
    person_id: str | None = None,
) -> dict[str, Any]:
    raw_wechat_id = clean_text(payload.get("wechat_id"))
    display_name = local_ui_display_text(
        payload.get("wechat_display_name") or payload.get("display_name")
    )
    person_name = local_ui_display_text(
        payload.get("person_name") or payload.get("name")
    )
    if raw_wechat_id and not (display_name or person_name):
        return {
            "status": "blocked",
            "error_code": "display_name_required",
            "requires_display_name": True,
            "message": "只拿到内部标识，缺少可显示微信名；不能保存成用户看不懂的内部 ID。",
            "safety": internal_people_safety_payload(config),
        }
    if not person_name:
        person_name = display_name
    if not person_name:
        return {
            "status": "blocked",
            "error_code": "person_name_required",
            "requires_display_name": True,
            "message": "请填写人员姓名或微信显示名。",
            "safety": internal_people_safety_payload(config),
        }
    existing = find_person_by_id(config, person_id) if person_id else None
    if person_id and existing is None:
        return {"status": "not_found", "person": {}}
    person = existing or find_person_by_name(config, person_name)
    if person is None:
        person = PersonConfig(person_name=person_name)
        config.internal_people.append(person)
    person.person_name = person_name
    person.wechat_display_name = display_name
    person.aliases = normalized_alias_input(
        payload.get("aliases"),
        extras=[person_name, display_name, payload.get("common_names")],
    )
    person.role = clean_text(payload.get("role")) or clean_text(person.role) or "我方人员"
    person.modules = clean_text_list(payload.get("modules"))
    person.enabled = parse_bool(payload.get("enabled"), True)
    person.notes = local_ui_display_text(payload.get("notes"))
    config.wx_cli.real_read_enabled = False
    if conn is not None:
        upsert_internal_person_aliases(conn, person)
    write_config_center_yaml(config)
    return {
        "status": "saved",
        "person": internal_person_public_payload(person, config, conn),
        "downstream_status": internal_people_downstream_status(config, conn),
        "readback_fields": [
            "person_id",
            "person_name",
            "wechat_display_name",
            "aliases",
            "role",
            "modules",
            "enabled",
            "notes",
        ],
        "real_read_enabled": False,
        "save_triggers_collection": False,
        "safety": internal_people_safety_payload(config),
    }


def disable_internal_person_payload(
    config: AppConfig, conn: sqlite3.Connection | None, person_id: str
) -> dict[str, Any]:
    person = find_person_by_id(config, person_id)
    if person is None:
        return {"status": "not_found", "person": {}}
    person.enabled = False
    config.wx_cli.real_read_enabled = False
    if conn is not None:
        for alias in normalized_person_aliases(person):
            conn.execute(
                "update people_aliases set enabled = 0 where role = 'internal' and alias = ?",
                (alias,),
            )
        conn.commit()
    write_config_center_yaml(config)
    return {
        "status": "disabled",
        "person": internal_person_public_payload(person, config, conn),
        "real_read_enabled": False,
        "save_triggers_collection": False,
        "safety": internal_people_safety_payload(config),
    }


def build_internal_person_suggestions(
    config: AppConfig, conn: sqlite3.Connection | None, query: str
) -> list[dict[str, Any]]:
    sources = internal_people_candidate_sources(config, conn)
    query_lower = query.lower()
    scored: list[dict[str, Any]] = []
    for candidate in sources:
        display = str(candidate["display_name"])
        aliases = set(candidate.get("aliases", []))
        matched = display == query or query in aliases
        fuzzy = query_lower in display.lower() or any(
            query_lower in str(alias).lower() for alias in aliases
        )
        if not (matched or fuzzy):
            continue
        confidence = "已匹配" if candidate["source"] == "people_library" and matched else "可能是"
        scored.append(internal_person_suggestion_item(config, conn, candidate, confidence))
    if not scored:
        scored.append(
            {
                "person_name": local_ui_display_text(query),
                "person_name_safe": redact_visible_text(query),
                "wechat_display_name": local_ui_display_text(query),
                "wechat_display_name_safe": redact_visible_text(query),
                "suggested_fields": {
                    "person_name": local_ui_display_text(query),
                    "person_name_safe": redact_visible_text(query),
                    "wechat_display_name": local_ui_display_text(query),
                    "wechat_display_name_safe": redact_visible_text(query),
                    "aliases": [local_ui_display_text(query)],
                    "aliases_safe": [redact_visible_text(query)],
                    "role": "我方人员",
                    "modules": [],
                },
                "common_names": [local_ui_display_text(query)],
                "common_names_safe": [redact_visible_text(query)],
                "aliases": [local_ui_display_text(query)],
                "aliases_safe": [redact_visible_text(query)],
                "role": "我方人员",
                "modules": [],
                "modules_safe": [],
                "recent_appearance": recent_appearance_payload(conn, query),
                "initial_identity": "待人工确认",
                "confidence": "未找到",
                "requires_display_name": False,
                "impact": internal_people_downstream_status(config, conn),
                "source_label": "可新建为我方人员",
            }
        )
    return scored[:5]


def internal_person_suggestion_item(
    config: AppConfig,
    conn: sqlite3.Connection | None,
    candidate: dict[str, Any],
    confidence: str,
) -> dict[str, Any]:
    display = local_ui_display_text(candidate["display_name"])
    aliases = unique_safe_member_names(list(candidate.get("aliases", [])) + [display])
    person_name = local_ui_display_text(candidate.get("person_name") or display)
    modules = [
        local_ui_display_text(module)
        for module in candidate.get("modules", [])
        if local_ui_display_text(module)
    ]
    return {
        "person_name": person_name,
        "person_name_safe": redact_visible_text(person_name),
        "wechat_display_name": display,
        "wechat_display_name_safe": redact_visible_text(display),
        "suggested_fields": {
            "person_name": person_name,
            "person_name_safe": redact_visible_text(person_name),
            "wechat_display_name": display,
            "wechat_display_name_safe": redact_visible_text(display),
            "aliases": aliases,
            "aliases_safe": [redact_visible_text(alias) for alias in aliases],
            "role": "我方人员",
            "modules": modules,
            "modules_safe": [redact_visible_text(module) for module in modules],
        },
        "common_names": aliases,
        "common_names_safe": [redact_visible_text(alias) for alias in aliases],
        "aliases": aliases,
        "aliases_safe": [redact_visible_text(alias) for alias in aliases],
        "role": "我方人员",
        "modules": modules,
        "modules_safe": [redact_visible_text(module) for module in modules],
        "recent_appearance": recent_appearance_payload(conn, display),
        "initial_identity": "我方人员" if confidence == "已匹配" else "待人工确认",
        "confidence": confidence,
        "requires_display_name": False,
        "impact": internal_people_downstream_status(config, conn),
        "source_label": candidate.get("source_label", "本地可见来源"),
    }


def internal_people_suggestion_contract() -> dict[str, Any]:
    return {
        "input_fields": ["wechat_id", "wechat_display_name", "display_name", "name", "query"],
        "source_label": "本地人员库 / 最近发送人 / 监控群 roster 或成员池",
        "confidence_values": ["已匹配", "可能是", "未找到"],
        "requires_display_name_when_internal_id_only": True,
        "returns_raw_identifier": False,
    }


def internal_people_candidate_sources(
    config: AppConfig, conn: sqlite3.Connection | None
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for person in config.internal_people:
        if not person.enabled:
            continue
        aliases = normalized_person_aliases(person)
        display = clean_text(person.wechat_display_name or person.person_name)
        if display:
            candidates.append(
                {
                    "display_name": display,
                    "person_name": person.person_name,
                    "aliases": aliases,
                    "modules": person.modules,
                    "source": "people_library",
                    "source_label": "已有我方人员库",
                }
            )
    for name in all_local_sender_display_names(config, conn):
        candidates.append(
            {
                "display_name": name,
                "person_name": name,
                "aliases": [name],
                "modules": [],
                "source": "local_senders",
                "source_label": "本地最近发送人",
            }
        )
    for session in config.sessions:
        options = monitor_group_member_options(conn, session, config)
        for name in options.get("names", []):
            candidates.append(
                {
                    "display_name": name,
                    "person_name": name,
                    "aliases": [name],
                    "modules": [session.module_name] if session.module_name else [],
                    "source": "monitor_group_members",
                    "source_label": "监控群成员池",
                }
            )
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        display = clean_text(candidate.get("display_name"))
        if not display:
            continue
        row = unique.setdefault(display, {**candidate, "aliases": [], "modules": []})
        row["aliases"] = unique_safe_member_names(
            list(row.get("aliases", [])) + list(candidate.get("aliases", []))
        )
        row["modules"] = unique_clean_text(
            list(row.get("modules", [])) + list(candidate.get("modules", []))
        )
    return list(unique.values())


def all_local_sender_display_names(
    config: AppConfig, conn: sqlite3.Connection | None
) -> list[str]:
    names: list[str] = []
    if conn is not None:
        try:
            rows = conn.execute(
                """
                select distinct sender_display_name
                from raw_messages
                order by sender_display_name
                """
            ).fetchall()
            names.extend(str(row["sender_display_name"] or "") for row in rows)
        except sqlite3.Error:
            pass
    for session in config.sessions:
        names.extend(latest_trial_member_names(config, session))
    return unique_safe_member_names(names)


def recent_appearance_payload(
    conn: sqlite3.Connection | None, display_name: str
) -> dict[str, Any]:
    if conn is None:
        return {"message_count": 0, "group_count": 0, "groups": []}
    try:
        rows = conn.execute(
            """
            select s.external_id, s.display_name, count(rm.id) as message_count
            from raw_messages rm
            join sessions s on s.id = rm.session_id
            where rm.sender_display_name = ?
            group by s.external_id, s.display_name
            order by message_count desc, s.display_name
            """,
            (display_name,),
        ).fetchall()
    except sqlite3.Error:
        return {"message_count": 0, "group_count": 0, "groups": []}
    groups = [
        {
            "group_id": f"mg-{hashlib.sha256(str(row['external_id']).encode('utf-8')).hexdigest()[:12]}",
            "group_name": local_group_display_meta(
                row["display_name"], source="recent_appearance"
            )["value"],
            "group_name_safe": redact_visible_text(
                local_group_display_meta(row["display_name"], source="recent_appearance")[
                    "value"
                ]
            ),
            "group_name_status": local_group_display_meta(
                row["display_name"], source="recent_appearance"
            )["status"],
            "group_name_reason_code": local_group_display_meta(
                row["display_name"], source="recent_appearance"
            )["reason_code"],
            "message_count": int(row["message_count"] or 0),
        }
        for row in rows
    ]
    return {
        "message_count": sum(group["message_count"] for group in groups),
        "group_count": len(groups),
        "groups": groups,
    }


def internal_person_impact_payload(
    config: AppConfig, conn: sqlite3.Connection | None, person: PersonConfig
) -> dict[str, Any]:
    aliases = set(normalized_person_aliases(person))
    group_count = len(
        [
            session
            for session in config.sessions
            if aliases.intersection(
                set(normalized_owner_names(session))
                | set(session.common_contacts)
                | set(session.internal_people)
                | set(getattr(session, "roster_member_names", []) or [])
            )
        ]
    )
    sender_count = 0
    if conn is not None and aliases:
        placeholders = ",".join("?" for _ in aliases)
        try:
            sender_count = int(
                conn.execute(
                    f"select count(*) from raw_messages where sender_display_name in ({placeholders})",
                    tuple(aliases),
                ).fetchone()[0]
                or 0
            )
        except sqlite3.Error:
            sender_count = 0
    return {
        "sender_message_count": sender_count,
        "monitor_group_count": group_count,
        "candidate_status": "身份映射可用于候选显示",
        "daily_status": "日报会使用更新后的身份映射",
        "transfer_status": "转述摘要会使用更新后的身份映射",
    }


def internal_people_downstream_status(
    config: AppConfig, conn: sqlite3.Connection | None
) -> dict[str, Any]:
    enabled_people = [person for person in config.internal_people if person.enabled]
    aliases = [alias for person in enabled_people for alias in normalized_person_aliases(person)]
    sender_match_count = 0
    if conn is not None and aliases:
        placeholders = ",".join("?" for _ in aliases)
        try:
            sender_match_count = int(
                conn.execute(
                    f"select count(*) from raw_messages where sender_display_name in ({placeholders})",
                    tuple(aliases),
                ).fetchone()[0]
                or 0
            )
        except sqlite3.Error:
            sender_match_count = 0
    return {
        "people_count": len(enabled_people),
        "alias_count": len(set(aliases)),
        "sender_match_count": sender_match_count,
        "group_option_count": len(
            {
                name
                for session in config.sessions
                for name in (
                    normalized_owner_names(session)
                    + session.common_contacts
                    + session.internal_people
                    + list(getattr(session, "roster_member_names", []) or [])
                )
            }
        ),
        "candidate_status": "已接入发送人识别",
        "daily_status": "日报读取同一身份库",
        "transfer_status": "转述摘要读取同一身份库",
    }


def internal_people_source_summary(
    config: AppConfig, conn: sqlite3.Connection | None
) -> dict[str, int]:
    return {
        "people_library_count": len([person for person in config.internal_people if person.enabled]),
        "local_sender_count": len(all_local_sender_display_names(config, conn)),
        "monitor_group_count": len(config.sessions),
        "roster_member_count": len(
            {
                name
                for session in config.sessions
                for name in unique_safe_member_names(
                    list(getattr(session, "roster_member_names", []) or [])
                )
            }
        ),
    }


def internal_people_safety_payload(config: AppConfig) -> dict[str, Any]:
    return {
        "save_triggers_collection": False,
        "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        "raw_identifier_returned": False,
        "formal_write_enabled": False,
    }


def normalized_person_aliases(person: PersonConfig) -> list[str]:
    return unique_safe_member_names(
        [person.person_name, person.wechat_display_name, *list(person.aliases or [])]
    )


def normalized_alias_input(value: Any, extras: list[Any] | None = None) -> list[str]:
    values: list[Any] = []
    if isinstance(value, list):
        values.extend(value)
    elif isinstance(value, str):
        text = value.replace("，", ",").replace("\r", "\n").replace(",", "\n")
        for line in text.splitlines():
            values.extend(part for part in line.split(" ") if part)
    for extra in extras or []:
        if isinstance(extra, list):
            values.extend(extra)
        else:
            values.append(extra)
    return unique_safe_member_names(values)


def find_person_by_id(config: AppConfig, person_id: str | None) -> PersonConfig | None:
    if not person_id:
        return None
    return next((person for person in config.internal_people if person_public_id(person) == person_id), None)


def find_person_by_name(config: AppConfig, person_name: str) -> PersonConfig | None:
    return next(
        (
            person
            for person in config.internal_people
            if clean_text(person.person_name) == clean_text(person_name)
        ),
        None,
    )


def person_public_id(person: PersonConfig) -> str:
    seed = clean_text(person.person_name) or clean_text(person.wechat_display_name)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"person-{digest}"


def upsert_internal_person_aliases(conn: sqlite3.Connection, person: PersonConfig) -> None:
    for alias in normalized_person_aliases(person):
        conn.execute(
            """
            insert into people_aliases (person_name, alias, role, enabled)
            values (?, ?, 'internal', ?)
            on conflict(alias, role) do update set
              person_name = excluded.person_name,
              enabled = excluded.enabled
            """,
            (person.person_name, alias, 1 if person.enabled else 0),
        )
    conn.commit()


def messages_v1_payload(
    config: AppConfig, conn: sqlite3.Connection, group_id: str = "all"
) -> dict[str, Any]:
    groups = message_group_options(config, conn)
    selected = group_id if group_id and group_id != "all" else "all"
    session_external = ""
    if selected != "all":
        session = find_monitor_group(config, selected)
        if session is None:
            return {
                "status": "not_found",
                "selected_group_id": selected,
                "group_filter_label": "单群消息",
                "group_count": len(groups),
                "groups_count": len(groups),
                "message_count": 0,
                "count": 0,
                "groups": groups,
                "messages": [],
                "empty_state_label": "未找到这个监控群，请先从群列表选择。",
                "group_first_contract": {
                    "requires_group_selection": True,
                    "single_group_no_fallback": True,
                    "all_groups_value": "all",
                },
                "safety": {
                    "content_returned": False,
                    "raw_payload_returned": False,
                    "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
                },
            }
        session_external = session.external_id
    query = """
        select rm.id, rm.sender_display_name, rm.sender_role, rm.sent_at,
               s.external_id, s.display_name, s.customer_name, s.module_name,
               count(cim.item_id) as candidate_count
        from raw_messages rm
        join sessions s on s.id = rm.session_id
        left join candidate_item_messages cim on cim.raw_message_id = rm.id
    """
    params: tuple[Any, ...] = ()
    if session_external:
        query += " where s.external_id = ?"
        params = (session_external,)
    query += """
        group by rm.id, rm.sender_display_name, rm.sender_role, rm.sent_at,
                 s.external_id, s.display_name, s.customer_name, s.module_name
        order by rm.sent_at desc, rm.id desc
        limit 100
    """
    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        rows = []
    messages = []
    for row in rows:
        row_group_id = f"mg-{hashlib.sha256(str(row['external_id']).encode('utf-8')).hexdigest()[:12]}"
        ref = f"m-{int(row['id']):04d}"
        group_meta = local_group_display_meta(row["display_name"], source="message_session")
        group_name = group_meta["value"]
        customer_label = local_ui_display_text(row["customer_name"] or "未标客户")
        module_label = local_ui_display_text(row["module_name"] or "未标模块")
        messages.append(
            {
                "message_ref": ref,
                "sent_at": str(row["sent_at"] or ""),
                "group_id": row_group_id,
                "group_name": group_name,
                "group_name_safe": redact_visible_text(group_name),
                "group_name_status": group_meta["status"],
                "group_name_reason_code": group_meta["reason_code"],
                "group_name_source_error_code": group_meta["source_error_code"],
                "customer_label": customer_label,
                "customer_label_safe": redact_visible_text(customer_label),
                "module_label": module_label,
                "module_label_safe": redact_visible_text(module_label),
                "sender_display_name": safe_sender_display(row["sender_display_name"]),
                "sender_identity": safe_sender_role(row["sender_role"]),
                "sender_identity_label": identity_label(row["sender_role"]),
                "candidate_count": int(row["candidate_count"] or 0),
                "detail_target": {"group_id": row_group_id, "message_ref": ref},
            }
        )
    return {
        "status": "ok",
        "selected_group_id": selected,
        "group_filter_label": "全部监控群" if selected == "all" else "单群消息",
        "count": len(messages),
        "message_count": len(messages),
        "group_count": len(groups),
        "groups_count": len(groups),
        "group_status": "all_groups" if selected == "all" else "single_group",
        "single_group_no_fallback": selected != "all",
        "empty_state_label": (
            "当前群暂无本地消息；不会回退展示全部群。"
            if selected != "all" and not messages
            else ""
        ),
        "group_first_contract": {
            "requires_group_selection": True,
            "single_group_no_fallback": True,
            "all_groups_value": "all",
            "filter_param": "group_id",
        },
        "groups": groups,
        "messages": messages,
        "safety": {
            "content_returned": False,
            "raw_payload_returned": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        },
    }


def message_group_options(
    config: AppConfig, conn: sqlite3.Connection
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    try:
        rows = conn.execute(
            """
            select s.external_id, count(rm.id) as message_count
            from sessions s
            left join raw_messages rm on rm.session_id = s.id
            group by s.external_id
            """
        ).fetchall()
        counts = {str(row["external_id"]): int(row["message_count"] or 0) for row in rows}
    except sqlite3.Error:
        counts = {}
    groups = [
        {
            "group_id": "all",
            "group_name": "全部监控群",
            "message_count": sum(counts.values()),
            "status_label": "全部群",
            "enabled": True,
        }
    ]
    for session in config.sessions:
        group_meta = local_group_display_meta(
            session.display_name,
            source=clean_text(getattr(session, "display_name_source", ""))
            or "config_display_name",
        )
        group_name = group_meta["value"]
        customer_label = local_ui_display_text(session.customer_name or "未标客户")
        module_label = local_ui_display_text(session.module_name or "未标模块")
        groups.append(
            {
                "group_id": monitor_group_public_id(session),
                "group_name": group_name,
                "group_name_safe": redact_visible_text(group_name),
                "display_name_status": group_meta["status"],
                "group_name_status": group_meta["status"],
                "group_name_reason_code": group_meta["reason_code"],
                "group_name_source_error_code": group_meta["source_error_code"],
                "customer_label": customer_label,
                "customer_label_safe": redact_visible_text(customer_label),
                "module_label": module_label,
                "module_label_safe": redact_visible_text(module_label),
                "enabled": bool(session.enabled),
                "archived": bool(getattr(session, "archived", False)),
                "status_label": monitor_group_status_label(session),
                "message_count": counts.get(session.external_id, 0),
            }
        )
    return groups


def identity_label(role: Any) -> str:
    return {
        "internal": "我方人员",
        "customer": "客户侧",
        "channel": "渠道侧",
        "unknown": "待确认",
    }.get(safe_sender_role(role), "待确认")


def windows_readiness_payload(config: AppConfig) -> dict[str, Any]:
    sample = Path(config.root) / "config" / "app.windows.example.yaml"
    readiness = wx_cli_readiness(config)
    mac_dev_detected = any(
        token in json.dumps(
            {
                "allowed_session": config.wx_cli.real_allowed_session,
                "sessions": [session.display_name for session in config.sessions],
                "wx_binary": config.wx_cli.binary,
                "database": config.database.path,
                "export": config.export.directory,
            },
            ensure_ascii=False,
        )
        for token in ["襄城县", "/Users/gd", "Mac"]
    )
    path_isolation = windows_path_isolation_payload(config, sample)
    wx_cli_summary = windows_wx_cli_summary_payload(config, readiness)
    isolation_ok = (
        sample.exists()
        and not mac_dev_detected
        and not config.wx_cli.real_read_enabled
        and path_isolation["status"] == "ok"
    )
    return {
        "status": "ok",
        "title": "Windows 可实战配置底座",
        "profile": "windows_formal",
        "runtime_environment": windows_runtime_environment_label(),
        "config_root": {
            "label": "项目根目录",
            "path_returned": False,
            "status": "hidden_for_safety",
        },
        "config_sample": "config/app.windows.example.yaml",
        "config_sample_exists": sample.exists(),
        "mac_development_config_detected": mac_dev_detected,
        "config_isolation_status": "ok" if isolation_ok else "needs_review",
        "mac_import_policy_label": "Windows 导入群默认待验证，未验证前不计入日报监控",
        "real_read_enabled": bool(config.wx_cli.real_read_enabled),
        "wx_cli": wx_cli_summary,
        "wechat_connection": {
            "status": wx_cli_summary["connection_status"],
            "label": wx_cli_summary["connection_label"],
            "session_count_returned": False,
            "message_read_executed": False,
        },
        "path_isolation": path_isolation,
        "ready_label": (
            "配置样例已就绪，默认不读取"
            if isolation_ok
            else "请先检查 Windows 配置隔离与真实读取开关"
        ),
        "checks": [
            {
                "key": "config_isolation",
                "label": "Windows 正式挂机配置与 Mac 开发配置分离",
                "passed": sample.exists() and not mac_dev_detected,
            },
            {
                "key": "no_mac_test_account",
                "label": "不混用 Mac 测试微信号配置",
                "passed": not mac_dev_detected,
            },
            {
                "key": "real_read_default_off",
                "label": "真实读取默认关闭",
                "passed": not config.wx_cli.real_read_enabled,
            },
            {
                "key": "path_isolation",
                "label": "数据 / 导出 / 日志 / 配置路径使用本项目隔离目录",
                "passed": path_isolation["status"] == "ok",
            },
        ],
        "safety": {
            "no_real_read_executed": True,
            "no_roster_sync_executed": True,
            "path_details_returned": False,
            "formal_write_enabled": False,
            "default_real_read_enabled": bool(config.wx_cli.real_read_enabled),
        },
    }


def windows_runtime_environment_label() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac_development"
    return "local_development"


def windows_wx_cli_summary_payload(
    config: AppConfig, readiness: dict[str, str]
) -> dict[str, Any]:
    mode = clean_text(config.wx_cli.mode) or "fixture"
    readiness_status = clean_text(readiness.get("status")) or "unknown"
    if mode == "fixture":
        fixture_path = resolve_safe_relative_config_path(config.wx_cli.fixture_dir)
        connection_status = "fixture_ready"
        connection_label = "fixture 模式只检查本地样例，不连接微信。"
    elif readiness_status == "ok":
        fixture_path = ""
        connection_status = "needs_connection_test"
        connection_label = "wx-cli 可执行；微信登录状态需在 Windows 本机连接测试确认。"
    else:
        fixture_path = ""
        connection_status = readiness_status
        connection_label = "wx-cli 暂不可用；未执行连接测试。"
    return {
        "mode": mode,
        "readiness_status": readiness_status,
        "binary_configured": readiness.get("binary_configured") == "true",
        "is_executable": readiness.get("is_executable") == "true",
        "connection_status": connection_status,
        "connection_label": connection_label,
        "fixture_location_label": fixture_path,
        "binary_path_returned": False,
        "message_read_executed": False,
    }


def windows_path_isolation_payload(config: AppConfig, sample: Path) -> dict[str, Any]:
    entries = [
        windows_path_entry("database", config.database.path, "data"),
        windows_path_entry("export", config.export.directory, "exports"),
        {
            "key": "logs",
            "label": "日志目录",
            "location_label": "logs",
            "relative": True,
            "mac_path_detected": False,
            "status": "ok",
        },
        {
            "key": "config_sample",
            "label": "Windows 配置样例",
            "location_label": "config/app.windows.example.yaml",
            "relative": True,
            "mac_path_detected": False,
            "status": "ok" if sample.exists() else "missing",
        },
    ]
    status = "ok" if all(entry["status"] == "ok" for entry in entries) else "needs_review"
    return {
        "status": status,
        "path_details_returned": False,
        "items": entries,
    }


def windows_path_entry(key: str, value: Any, expected_prefix: str) -> dict[str, Any]:
    raw = clean_text(value)
    path = Path(raw) if raw else Path()
    is_relative = bool(raw) and not path.is_absolute()
    mac_path_detected = "/Users/gd" in raw or raw.lower().startswith("/users/")
    starts_expected = raw == expected_prefix or raw.startswith(f"{expected_prefix}/")
    status = "ok" if is_relative and not mac_path_detected and starts_expected else "needs_review"
    return {
        "key": key,
        "label": {"database": "数据目录", "export": "导出目录"}.get(key, key),
        "location_label": resolve_safe_relative_config_path(raw),
        "relative": is_relative,
        "mac_path_detected": mac_path_detected,
        "status": status,
    }


def resolve_safe_relative_config_path(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    windows_drive_absolute = len(raw) > 2 and raw[1] == ":" and raw[2] in {"/", "\\"}
    if (
        "/Users/" in raw
        or "\\Users\\" in raw
        or Path(raw).is_absolute()
        or windows_drive_absolute
    ):
        return "[路径已脱敏]"
    return raw


def config_center_payload(
    config: AppConfig, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    enabled_whitelist_count = len(
        [s for s in config.sessions if s.enabled and s.is_whitelisted]
    )
    readiness = wx_cli_readiness(config)
    customer_data = customer_options_with_source_payload(config)
    customer_options = customer_data["options"]
    return {
        "status": {
            "mode": config.wx_cli.mode,
            "real_read_enabled": bool(config.wx_cli.real_read_enabled),
            "wx_cli_status": readiness["status"],
            "enabled_whitelist_count": enabled_whitelist_count,
            "latest_trial": latest_real_trial_config_center_summary(config),
            "persistent_authorization": persistent_real_read_contract_payload(config),
        },
        "editable": {
            "sessions": [
                config_center_session_payload(session, conn, config)
                for session in config.sessions
            ],
            "customer_options": customer_options,
            "customer_options_count": len(customer_options),
            "customer_source_status": customer_data["source_status"],
            "customer_source_error_code": customer_data["source_error_code"],
            "customer_option_sources": customer_data["sources"],
            "internal_people": [
                {
                    "person_name": person.person_name,
                    "wechat_display_name": person.wechat_display_name,
                    "aliases": list(person.aliases),
                    "role": person.role,
                    "modules": list(person.modules),
                    "enabled": bool(person.enabled),
                    "notes": getattr(person, "notes", ""),
                }
                for person in config.internal_people
            ],
            "risk": {
                "keywords": list(config.risk.keywords),
                "sensitive_keywords": list(config.risk.sensitive_keywords),
            },
            "trial_defaults": {
                "lookback_hours": min(
                    max(1, int(config.wx_cli.real_lookback_hours)),
                    LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
                ),
                "limit": min(
                    max(1, int(config.wx_cli.real_limit)),
                    LEGACY_REAL_TRIAL_MAX_LIMIT,
                ),
                "start_at": config.wx_cli.real_start_at,
                "end_at": config.wx_cli.real_end_at,
                "expanded_trial": expanded_real_trial_contract_payload(config),
                "persistent_authorization": persistent_real_read_contract_payload(config),
            },
        },
        "customer_options": customer_options,
        "customer_options_count": len(customer_options),
        "customer_source_status": customer_data["source_status"],
        "customer_source_error_code": customer_data["source_error_code"],
        "customer_option_sources": customer_data["sources"],
        "safety": {
            "default_real_read_enabled": False,
            "save_triggers_collection": False,
            "requires_confirmation": True,
            "max_limit": LEGACY_REAL_TRIAL_MAX_LIMIT,
            "max_lookback_hours": LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
            "requires_single_enabled_whitelist": True,
            "expanded_trial": expanded_real_trial_contract_payload(config),
            "persistent_real_read": persistent_real_read_contract_payload(config),
            "fixture_service_notice": config.wx_cli.mode != "real",
        },
        "save_target": "config/app.yaml",
    }


def config_center_session_payload(
    session: SessionConfig,
    conn: sqlite3.Connection | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    member_options = monitor_group_member_options(conn, session, config)
    group_meta = local_group_display_meta(
        session.display_name,
        source=clean_text(getattr(session, "display_name_source", ""))
        or "config_display_name",
    )
    return {
        "external_id": session.external_id,
        "display_name": group_meta["value"],
        "display_name_status": group_meta["status"],
        "display_name_source": group_meta["source"],
        "display_name_reason_code": group_meta["reason_code"],
        "display_name_source_error_code": group_meta["source_error_code"],
        "customer_name": session.customer_name,
        "channel_name": session.channel_name,
        "module_name": session.module_name,
        "owner_name": primary_owner_name(session),
        "owner_names": normalized_owner_names(session),
        "customer_stage": session.customer_stage,
        "group_type": session.group_type,
        "common_contacts": list(session.common_contacts),
        "reply_notes": session.reply_notes,
        "is_whitelisted": bool(session.is_whitelisted),
        "enabled": bool(session.enabled),
        "verification_status": safe_verification_status(session.verification_status),
        "daily_monitor_enabled": bool(session.daily_monitor_enabled),
        "include_in_daily": bool(session.include_in_daily),
        "trial_scope": session.trial_scope,
        "internal_people": list(session.internal_people),
        "archived": bool(getattr(session, "archived", False)),
        "customer_id": local_customer_id(session.customer_name),
        "customer_options": customer_options_payload(config) if config else [],
        "customer_options_count": len(customer_options_payload(config)) if config else 0,
        "customer_suggestion": customer_suggestion_payload(
            group_meta["value"] if group_meta["status"] == "resolved" else "",
            config,
        ),
        "member_options": monitor_group_member_options_summary(member_options),
        "member_options_detail_endpoint": f"/api/monitor-groups/{monitor_group_public_id(session)}",
        "member_list_returned": False,
    }


def save_config_center_payload(
    config: AppConfig,
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    sessions_payload = payload.get("sessions")
    if isinstance(sessions_payload, list):
        config.sessions = [
            SessionConfig(
                external_id=clean_text(item.get("external_id")),
                display_name=clean_text(item.get("display_name")),
                customer_name=clean_text(item.get("customer_name")),
                channel_name=clean_text(item.get("channel_name")),
                module_name=clean_text(item.get("module_name")),
                owner_name=primary_owner_from_payload(item),
                owner_names=clean_text_list(
                    item.get("owner_names", item.get("owner_name"))
                ),
                customer_stage=clean_text(item.get("customer_stage")),
                group_type=clean_text(item.get("group_type")),
                common_contacts=clean_text_list(item.get("common_contacts")),
                reply_notes=clean_text(item.get("reply_notes")),
                is_whitelisted=bool(item.get("is_whitelisted", True)),
                enabled=bool(item.get("enabled", True)),
                verification_status=safe_verification_status(
                    item.get("verification_status")
                ),
                daily_monitor_enabled=parse_bool(
                    item.get("daily_monitor_enabled"), True
                ),
                include_in_daily=parse_bool(item.get("include_in_daily"), True),
                trial_scope=clean_text(item.get("trial_scope")) or "最近50条",
                internal_people=clean_text_list(item.get("internal_people")),
                roster_member_names=clean_text_list(item.get("roster_member_names")),
                archived=parse_bool(item.get("archived"), False),
                display_name_status=clean_text(item.get("display_name_status"))
                or local_group_display_meta(item.get("display_name"))["status"],
                display_name_source=clean_text(item.get("display_name_source")),
                display_name_reason_code=clean_text(
                    item.get("display_name_reason_code")
                )
                or local_group_display_meta(item.get("display_name"))["reason_code"],
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
                wechat_display_name=safe_member_display_name(
                    item.get("wechat_display_name") or item.get("display_name")
                ),
                aliases=normalized_alias_input(item.get("aliases")),
                role=clean_text(item.get("role")) or "我方人员",
                modules=clean_text_list(item.get("modules")),
                enabled=parse_bool(item.get("enabled"), True),
                notes=redact_visible_text(clean_text(item.get("notes"))),
            )
            for item in people_payload
            if isinstance(item, dict) and clean_text(item.get("person_name"))
        ]
        if conn is not None:
            for person in config.internal_people:
                upsert_internal_person_aliases(conn, person)

    risk_payload = payload.get("risk", {})
    if isinstance(risk_payload, dict):
        config.risk = RiskConfig(
            keywords=clean_text_list(risk_payload.get("keywords")),
            sensitive_keywords=clean_text_list(risk_payload.get("sensitive_keywords")),
        )

    trial_defaults = payload.get("trial_defaults", {})
    if isinstance(trial_defaults, dict):
        config.wx_cli.real_lookback_hours = clamp_int(
            trial_defaults.get("lookback_hours"),
            minimum=1,
            maximum=LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
            default=LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
        )
        config.wx_cli.real_limit = clamp_int(
            trial_defaults.get("limit"),
            minimum=1,
            maximum=LEGACY_REAL_TRIAL_MAX_LIMIT,
            default=LEGACY_REAL_TRIAL_MAX_LIMIT,
        )
        config.wx_cli.real_start_at = clean_text(trial_defaults.get("start_at"))
        config.wx_cli.real_end_at = clean_text(trial_defaults.get("end_at"))
        expanded_defaults = trial_defaults.get("expanded_trial", {})
    else:
        expanded_defaults = {}
    payload_expanded_defaults = payload.get("expanded_trial_defaults", {})
    if isinstance(payload_expanded_defaults, dict) and payload_expanded_defaults:
        expanded_defaults = payload_expanded_defaults
    if isinstance(expanded_defaults, dict):
        config.wx_cli.expanded_real_lookback_days = clamp_float(
            expanded_defaults.get("max_lookback_days")
            or expanded_defaults.get("max_allowed_lookback_days")
            or expanded_defaults.get("lookback_days"),
            minimum=0.01,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_SAFETY_DAYS,
            default=30,
        )
        config.wx_cli.expanded_real_max_groups = clamp_int(
            expanded_defaults.get("max_groups"),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_GROUPS,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_GROUPS,
        )
        config.wx_cli.expanded_real_max_total_messages = clamp_int(
            expanded_defaults.get("max_total_messages"),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_TOTAL_MESSAGES,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_TOTAL_MESSAGES,
        )
        config.wx_cli.expanded_real_max_messages_per_group = clamp_int(
            expanded_defaults.get("max_messages_per_group"),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_MESSAGES_PER_GROUP,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_MESSAGES_PER_GROUP,
        )
        config.wx_cli.expanded_real_batch_limit = clamp_int(
            expanded_defaults.get("batch_limit")
            or expanded_defaults.get("max_batches"),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_BATCHES,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_BATCH_LIMIT,
        )

    persistent_defaults = payload.get("persistent_real_read", {})
    if not isinstance(persistent_defaults, dict) or not persistent_defaults:
        persistent_defaults = payload.get("persistent_authorization", {})
    if not isinstance(persistent_defaults, dict) or not persistent_defaults:
        persistent_defaults = (
            trial_defaults.get("persistent_real_read", {})
            if isinstance(trial_defaults, dict)
            else {}
        )
    if not isinstance(persistent_defaults, dict) or not persistent_defaults:
        persistent_defaults = (
            trial_defaults.get("persistent_authorization", {})
            if isinstance(trial_defaults, dict)
            else {}
        )
    if isinstance(persistent_defaults, dict) and persistent_defaults:
        config.wx_cli.persistent_real_read_enabled = parse_bool(
            persistent_defaults.get(
                "enabled",
                persistent_defaults.get("persistent_real_read_enabled"),
            ),
            bool(getattr(config.wx_cli, "persistent_real_read_enabled", False)),
        )
        config.wx_cli.persistent_real_read_paused = parse_bool(
            persistent_defaults.get(
                "paused",
                persistent_defaults.get("persistent_real_read_paused"),
            ),
            bool(getattr(config.wx_cli, "persistent_real_read_paused", False)),
        )
        config.wx_cli.persistent_real_read_test_account_confirmed = parse_bool(
            persistent_defaults.get(
                "test_account_confirmed",
                persistent_defaults.get("test_wechat_account_confirmed"),
            ),
            bool(
                getattr(
                    config.wx_cli,
                    "persistent_real_read_test_account_confirmed",
                    False,
                )
            ),
        )
        config.wx_cli.persistent_real_read_schedule_enabled = parse_bool(
            persistent_defaults.get(
                "schedule_enabled",
                persistent_defaults.get("persistent_real_read_schedule_enabled"),
            ),
            bool(
                getattr(config.wx_cli, "persistent_real_read_schedule_enabled", False)
            ),
        )
        config.wx_cli.persistent_real_read_interval_minutes = clamp_int(
            persistent_defaults.get(
                "interval_minutes",
                persistent_defaults.get("schedule_interval_minutes"),
            ),
            minimum=5,
            maximum=24 * 60,
            default=persistent_real_read_interval_minutes(config),
        )
        config.wx_cli.persistent_real_read_default_lookback_days = clamp_float(
            persistent_defaults.get(
                "default_lookback_days",
                persistent_defaults.get("lookback_days"),
            ),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_SAFETY_DAYS,
            default=persistent_real_read_default_lookback_days(config),
        )

    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": "saved",
        "real_read_enabled": False,
        "saved_to": "config/app.yaml",
        "editable": config_center_payload(config, conn)["editable"],
    }


def expanded_real_trial_caps(config: AppConfig) -> dict[str, Any]:
    return {
        "max_allowed_lookback_days": clamp_float(
            getattr(config.wx_cli, "expanded_real_lookback_days", 30),
            minimum=0.01,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_SAFETY_DAYS,
            default=30,
        ),
        "max_groups": clamp_int(
            getattr(config.wx_cli, "expanded_real_max_groups", 20),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_GROUPS,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_GROUPS,
        ),
        "max_total_messages": clamp_int(
            getattr(config.wx_cli, "expanded_real_max_total_messages", 5000),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_TOTAL_MESSAGES,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_TOTAL_MESSAGES,
        ),
        "max_messages_per_group": clamp_int(
            getattr(config.wx_cli, "expanded_real_max_messages_per_group", 500),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_MESSAGES_PER_GROUP,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_MAX_MESSAGES_PER_GROUP,
        ),
        "batch_limit": clamp_int(
            getattr(config.wx_cli, "expanded_real_batch_limit", 1),
            minimum=1,
            maximum=CONFIGURABLE_REAL_TRIAL_HARD_MAX_BATCHES,
            default=CONFIGURABLE_REAL_TRIAL_DEFAULT_BATCH_LIMIT,
        ),
    }


def persistent_real_read_interval_minutes(config: AppConfig) -> int:
    return clamp_int(
        getattr(config.wx_cli, "persistent_real_read_interval_minutes", 60),
        minimum=5,
        maximum=24 * 60,
        default=60,
    )


def persistent_real_read_default_lookback_days(config: AppConfig) -> float:
    return clamp_float(
        getattr(config.wx_cli, "persistent_real_read_default_lookback_days", 30),
        minimum=1,
        maximum=CONFIGURABLE_REAL_TRIAL_HARD_SAFETY_DAYS,
        default=30,
    )


def expanded_real_trial_contract_payload(config: AppConfig) -> dict[str, Any]:
    caps = expanded_real_trial_caps(config)
    return {
        "supported": True,
        "scope_mode": "configurable_window",
        "default_preset": "last_30_days",
        "default_preset_lookback_days": min(30, caps["max_allowed_lookback_days"]),
        "default_real_read_enabled": False,
        "one_time_only": True,
        "multi_group_supported": True,
        "supports_lookback_days": True,
        "supports_start_end_time": True,
        "test_wechat_account_required": True,
        "authorization_required": True,
        "one_time_authorization_token_required": True,
        "execute_once_field": "execute_once",
        "will_execute_without_explicit_authorization": False,
        "max_allowed_lookback_days": caps["max_allowed_lookback_days"],
        "max_lookback_days": caps["max_allowed_lookback_days"],
        "max_groups": caps["max_groups"],
        "max_total_messages": caps["max_total_messages"],
        "max_messages_per_group": caps["max_messages_per_group"],
        "batch_limit": caps["batch_limit"],
        "windows_config_fields": {
            "max_allowed_lookback_days": "wx_cli.expanded_real_lookback_days",
            "max_groups": "wx_cli.expanded_real_max_groups",
            "max_total_messages": "wx_cli.expanded_real_max_total_messages",
            "max_messages_per_group": "wx_cli.expanded_real_max_messages_per_group",
            "batch_limit": "wx_cli.expanded_real_batch_limit",
        },
    }


def persistent_real_read_contract_payload(config: AppConfig) -> dict[str, Any]:
    caps = expanded_real_trial_caps(config)
    enabled = bool(getattr(config.wx_cli, "persistent_real_read_enabled", False))
    paused = bool(getattr(config.wx_cli, "persistent_real_read_paused", False))
    schedule_enabled = bool(
        getattr(config.wx_cli, "persistent_real_read_schedule_enabled", False)
    )
    default_lookback = persistent_real_read_default_lookback_days(config)
    return {
        "supported": True,
        "authorization_mode": "persistent",
        "enabled": enabled,
        "paused": paused,
        "status": "paused" if enabled and paused else ("enabled" if enabled else "disabled"),
        "status_label": (
            "已暂停长期真实读取"
            if enabled and paused
            else ("已开启长期真实读取授权" if enabled else "长期真实读取默认关闭")
        ),
        "test_account_confirmed": bool(
            getattr(config.wx_cli, "persistent_real_read_test_account_confirmed", False)
        ),
        "trigger_modes": ["manual", "scheduled"],
        "manual_trigger_enabled": enabled and not paused,
        "schedule_enabled": schedule_enabled,
        "interval_minutes": persistent_real_read_interval_minutes(config),
        "default_lookback_days": default_lookback,
        "max_allowed_lookback_days": caps["max_allowed_lookback_days"],
        "max_groups": caps["max_groups"],
        "max_total_messages": caps["max_total_messages"],
        "max_messages_per_group": caps["max_messages_per_group"],
        "batch_limit": caps["batch_limit"],
        "multi_group_supported": True,
        "default_scope_mode": "enabled_whitelist",
        "supported_scope_modes": ["enabled_whitelist", "all_wechat_groups"],
        "uses_enabled_whitelist_only": False,
        "all_wechat_groups_scope_supported": True,
        "all_wechat_groups_source": "wx_cli_sessions_probe",
        "all_wechat_groups_filters_non_group_sessions": True,
        "all_wechat_groups_returns_group_list": False,
        "all_wechat_groups_can_upsert_local_monitor_groups": True,
        "writes_local_raw_normalized_candidate": True,
        "formal_write_enabled": False,
        "no_external_send": True,
        "no_auto_reply": True,
        "will_execute_without_persistent_authorization": False,
        "returns_sensitive_details": False,
        "real_read_enabled_after": False,
        "windows_config_fields": {
            "enabled": "wx_cli.persistent_real_read_enabled",
            "paused": "wx_cli.persistent_real_read_paused",
            "test_account_confirmed": "wx_cli.persistent_real_read_test_account_confirmed",
            "schedule_enabled": "wx_cli.persistent_real_read_schedule_enabled",
            "interval_minutes": "wx_cli.persistent_real_read_interval_minutes",
            "default_lookback_days": "wx_cli.persistent_real_read_default_lookback_days",
            "max_allowed_lookback_days": "wx_cli.expanded_real_lookback_days",
        },
    }


def normalized_authorization_mode(payload: dict[str, Any]) -> str:
    raw = clean_text(
        payload.get("authorization_mode")
        or payload.get("auth_mode")
        or payload.get("real_read_authorization_mode")
    )
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"persistent", "persistent_real_read", "long_term", "longterm"}:
        return "persistent"
    return "one_time"


def normalized_real_trial_scope_mode(payload: dict[str, Any]) -> str:
    raw = clean_text(
        payload.get("scope_mode")
        or payload.get("trial_mode")
        or payload.get("mode")
        or payload.get("preset")
    )
    normalized = (
        raw.lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )
    compact = normalized.replace("_", "")
    if normalized in CONFIGURABLE_REAL_TRIAL_PRESETS or compact in CONFIGURABLE_REAL_TRIAL_PRESETS:
        return "configurable_window"
    if normalized in ALL_WECHAT_GROUP_SCOPE_ALIASES or compact in ALL_WECHAT_GROUP_SCOPE_ALIASES:
        return "all_wechat_groups"
    if parse_bool(payload.get("include_all_detected_groups"), False) or parse_bool(
        payload.get("include_all_wechat_groups"),
        False,
    ):
        return "all_wechat_groups"
    return "legacy_recent50"


def requested_group_tokens(payload: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "group_ids",
        "monitor_group_ids",
        "whitelist_group_ids",
        "session_ids",
        "sessions",
        "groups",
    ):
        value = payload.get(key)
        if not value:
            continue
        if isinstance(value, list):
            values.extend(value)
        else:
            values.append(value)

    tokens: list[str] = []
    for value in values:
        if isinstance(value, dict):
            for key in ("external_id", "group_id", "id", "display_name", "name"):
                token = clean_text(value.get(key))
                if token:
                    tokens.append(token)
        else:
            tokens.extend(clean_text_list(value))
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def expanded_trial_blocked(
    error_code: str,
    message: str,
    *,
    selected_group_count: int = 0,
    window_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window_summary = window_summary or {}
    return {
        "status": "blocked",
        "will_run": False,
        "real_read_enabled": False,
        "real_read_enabled_after": False,
        "error_code": error_code,
        "reason_code": error_code,
        "message": message,
        "scope": {
            "scope_mode": "configurable_window",
            "selected_group_count": selected_group_count,
            "groups_returned": False,
            "session_names_returned": False,
            **window_summary,
        },
        "limits": window_summary,
        "failure_summary": {
            "status": "blocked",
            "error_code": error_code,
            "error_count": 1,
            "failed_group_count": selected_group_count,
            "details_returned": False,
        },
    }


def parse_trial_int(value: Any, default: int, error_code: str) -> tuple[int | None, str | None]:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return None, error_code
    return parsed, None


def parse_trial_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{normalized}T00:00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ceil_days(delta: timedelta) -> int:
    seconds = delta.total_seconds()
    if seconds <= 0:
        return 0
    full_days = int(seconds // 86400)
    return full_days if seconds % 86400 == 0 else full_days + 1


def trial_window_summary(
    payload: dict[str, Any],
    caps: dict[str, int],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    max_allowed = caps["max_allowed_lookback_days"]
    start_raw = clean_text(payload.get("start_time") or payload.get("start_at"))
    end_raw = clean_text(payload.get("end_time") or payload.get("end_at"))
    lookback_provided = clean_text(payload.get("lookback_days")) != ""
    if start_raw or end_raw:
        if not (start_raw and end_raw):
            return None, "expanded_trial_time_range_invalid"
        start_at = parse_trial_datetime(start_raw)
        end_at = parse_trial_datetime(end_raw)
        if start_at is None or end_at is None or end_at <= start_at:
            return None, "expanded_trial_time_range_invalid"
        effective_days = ceil_days(end_at - start_at)
        requested_days = effective_days
    else:
        requested_days, error_code = parse_trial_int(
            payload.get("lookback_days"),
            30,
            "expanded_trial_lookback_days_invalid",
        )
        if error_code or requested_days is None or requested_days < 1:
            return None, "expanded_trial_lookback_days_invalid"
        effective_days = requested_days
        end_at = now or datetime.now(timezone.utc)
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        end_at = end_at.astimezone(timezone.utc)
        start_at = end_at - timedelta(days=effective_days)

    limit_reason = "within_configured_limit"
    if effective_days > max_allowed:
        limit_reason = "exceeds_configured_lookback"
    return {
        "requested_lookback_days": requested_days,
        "effective_lookback_days": effective_days,
        "max_allowed_lookback_days": max_allowed,
        "max_lookback_days": max_allowed,
        "window_start": start_at.isoformat(timespec="seconds"),
        "window_end": end_at.isoformat(timespec="seconds"),
        "limit_reason": limit_reason,
        "time_range_mode": "explicit_range" if start_raw or end_raw else "lookback_days",
        "default_window_used": not lookback_provided and not (start_raw or end_raw),
    }, None


def execution_requested(payload: dict[str, Any]) -> bool:
    return any(
        parse_bool(payload.get(key), False)
        for key in (
            "execute_once",
            "run_once",
            "execute_real_trial_once",
            "open_execution_path",
        )
    )


def one_time_authorization_present(payload: dict[str, Any]) -> bool:
    marker = any(
        parse_bool(payload.get(key), False)
        for key in (
            "one_time_authorization_marker",
            "one_time_authorization_confirmed",
            "authorization_marker",
        )
    )
    token = clean_text(
        payload.get("one_time_authorization_token")
        or payload.get("authorization_token")
        or payload.get("one_time_token")
    )
    return marker or bool(token)


def history_since_text(window_summary: dict[str, Any]) -> str:
    start = parse_trial_datetime(window_summary.get("window_start"))
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(
            days=int(window_summary.get("effective_lookback_days") or 1)
        )
    return start.astimezone().strftime("%Y-%m-%d %H:%M")


def configurable_history_args(
    session: SessionConfig, window_summary: dict[str, Any], limit: int
) -> list[str]:
    return [
        "history",
        session.display_name or session.external_id,
        "--since",
        history_since_text(window_summary),
        "-n",
        str(limit),
        "--json",
    ]


def execution_summary_from_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "__dict__"):
        data = dict(result.__dict__)
    elif isinstance(result, dict):
        data = dict(result)
    else:
        data = {}
    status = clean_text(data.get("status")) or "failed"
    error_code = clean_text(data.get("error_code"))
    return {
        "status": status,
        "error_code": error_code,
        "sessions_total": int(data.get("sessions_total") or 0),
        "sessions_success": int(data.get("sessions_success") or 0),
        "sessions_failed": int(data.get("sessions_failed") or 0),
        "raw_messages_seen": int(data.get("raw_messages_seen") or 0),
        "raw_messages_inserted": int(data.get("raw_messages_inserted") or 0),
        "raw_messages_duplicated": int(data.get("raw_messages_duplicated") or 0),
        "candidate_items_created": int(data.get("candidate_items_created") or 0),
        "candidate_items_updated": int(data.get("candidate_items_updated") or 0),
    }


def execute_configurable_real_trial_once(
    config: AppConfig,
    conn: sqlite3.Connection | None,
    selected_sessions: list[SessionConfig],
    window_summary: dict[str, Any],
    limits: dict[str, int],
    *,
    collection_mode: str = "real_trial_once",
) -> dict[str, Any]:
    if conn is None:
        return {
            "status": "blocked",
            "error_code": "real_trial_execution_entry_unavailable",
            "sessions_total": len(selected_sessions),
            "sessions_success": 0,
            "sessions_failed": len(selected_sessions),
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        }
    if config.wx_cli.mode != "real":
        return {
            "status": "blocked",
            "error_code": "real_trial_real_mode_required",
            "sessions_total": len(selected_sessions),
            "sessions_success": 0,
            "sessions_failed": len(selected_sessions),
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        }

    connection = test_connection(config)
    if connection["status"] != "ok":
        return {
            "status": "failed",
            "error_code": clean_text(connection.get("error_code")) or connection["status"],
            "sessions_total": len(selected_sessions),
            "sessions_success": 0,
            "sessions_failed": len(selected_sessions),
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        }

    messages = []
    failed = 0
    for session in selected_sessions:
        result = run_wx_cli_json(
            config,
            configurable_history_args(
                session,
                window_summary,
                int(limits["requested_messages_per_group"]),
            ),
        )
        if result.status != "ok":
            failed += 1
            continue
        messages.extend(map_history_payload(result.parsed, session))

    if failed and not messages:
        return {
            "status": "failed",
            "error_code": "real_trial_history_failed",
            "sessions_total": len(selected_sessions),
            "sessions_success": 0,
            "sessions_failed": failed,
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        }

    collected = collect_normalized_messages(
        config,
        conn,
        messages,
        mode=collection_mode,
    )
    summary = execution_summary_from_result(collected)
    summary["sessions_total"] = len(selected_sessions)
    summary["sessions_failed"] = failed
    summary["sessions_success"] = max(0, len(selected_sessions) - failed)
    summary["status"] = "partial_failed" if failed else summary["status"]
    summary["error_code"] = "real_trial_partial_failed" if failed else summary["error_code"]
    return summary


def session_probe_payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = []
        for key in ("sessions", "items", "data", "chats", "rooms", "contacts"):
            child = payload.get(key)
            if isinstance(child, list):
                values = child
                break
        if not values and any(key in payload for key in ("id", "name", "display_name")):
            values = [payload]
    else:
        values = []
    return [item for item in values if isinstance(item, dict)]


def session_probe_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean_text(item.get(key))
        if value:
            return value
    return ""


def session_probe_type_text(item: dict[str, Any]) -> str:
    return " ".join(
        clean_text(item.get(key)).lower()
        for key in (
            "type",
            "kind",
            "category",
            "chat_type",
            "session_type",
            "conversation_type",
        )
        if clean_text(item.get(key))
    )


def session_probe_type_tokens(item: dict[str, Any]) -> set[str]:
    text = session_probe_type_text(item).replace("-", " ").replace("_", " ")
    return {token for token in text.split() if token}


def session_probe_has_text(item: dict[str, Any], *keys: str) -> bool:
    return any(bool(clean_text(item.get(key))) for key in keys)


def is_detected_wechat_group_session(item: dict[str, Any]) -> bool:
    type_text = session_probe_type_text(item)
    type_tokens = session_probe_type_tokens(item)
    identifier = session_probe_text(
        item,
        "id",
        "external_id",
        "username",
        "room_id",
        "chat_id",
        "conversation_id",
        "session_id",
    )
    display = session_probe_text(item, *READABLE_SESSION_NAME_KEYS)
    identifier_text = identifier.lower()
    display_text = display.lower()
    haystack = f"{type_text} {identifier_text} {display_text}".lower()
    if any(
        token in haystack
        for token in ("filehelper", "文件传输助手")
    ):
        return False
    if any(
        token in type_text
        for token in (
            "official",
            "public",
            "subscription",
            "service_account",
            "mp",
            "single",
            "friend",
            "private",
            "contact",
            "system",
        )
    ):
        return False
    if any(
        token in display_text
        for token in (
            "公众号",
            "单聊",
        )
    ):
        return False
    for key in ("is_group", "is_group_chat", "group", "is_chatroom"):
        if parse_bool(item.get(key), False):
            return True
    if "@chatroom" in identifier_text:
        return True
    if "chatroom" in type_tokens or type_text in {"chatroom", "wechat_chatroom"}:
        return True
    if "group" in type_tokens or type_text in {"group", "wechat_group", "group_chat"}:
        return True
    if session_probe_has_text(item, "room_id", "chatroom_id"):
        return True
    return any(token in display for token in ("微信群", "群聊"))


def detected_group_identifier(item: dict[str, Any], index: int) -> str:
    raw = session_probe_text(
        item,
        "id",
        "external_id",
        "username",
        "room_id",
        "chat_id",
        "conversation_id",
        "session_id",
    ) or session_probe_text(item, *READABLE_SESSION_NAME_KEYS)
    digest = hashlib.sha256((raw or f"detected-{index}").encode("utf-8")).hexdigest()[:12]
    return f"detected-wechat-group-{digest}"


def detected_group_readable_display_name(item: dict[str, Any]) -> tuple[str, str]:
    for key in READABLE_SESSION_NAME_KEYS:
        value = clean_text(item.get(key))
        if value and not is_internal_identifier_for_display(value):
            return value, key
    return "", ""


def detected_group_display_meta(item: dict[str, Any], index: int) -> dict[str, str]:
    del index
    display, source = detected_group_readable_display_name(item)
    if display:
        return local_group_display_meta(display, source=source)
    return {
        "value": GROUP_DISPLAY_PLACEHOLDER,
        "status": "unresolved",
        "reason_code": "internal_identifier_only",
        "source_error_code": "group_display_name_unresolved",
        "source": "session_probe",
    }


def detected_wechat_group_sessions(payload: Any) -> tuple[list[SessionConfig], dict[str, Any]]:
    items = session_probe_payload_items(payload)
    selected: list[SessionConfig] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not is_detected_wechat_group_session(item):
            continue
        external_id = detected_group_identifier(item, index)
        if external_id in seen:
            continue
        seen.add(external_id)
        display_meta = detected_group_display_meta(item, index)
        selected.append(
            SessionConfig(
                external_id=external_id,
                display_name=display_meta["value"],
                group_type="微信群",
                is_whitelisted=False,
                enabled=True,
                verification_status="pending_verification",
                daily_monitor_enabled=False,
                include_in_daily=False,
                trial_scope="全部微信群首跑",
                display_name_status=display_meta["status"],
                display_name_source=display_meta["source"],
                display_name_reason_code=display_meta["reason_code"],
            )
        )
    summary = {
        "source_status": clean_text(payload.get("status")) if isinstance(payload, dict) else "ok",
        "source_error_code": clean_text(payload.get("error_code")) if isinstance(payload, dict) else "",
        "detected_session_count": len(items),
        "detected_group_count": len(selected),
        "excluded_non_group_count": max(0, len(items) - len(selected)),
        "unresolved_display_name_count": len(
            [
                session
                for session in selected
                if getattr(session, "display_name_status", "") == "unresolved"
            ]
        ),
        "groups_returned": False,
        "session_names_returned": False,
    }
    if not summary["source_status"]:
        summary["source_status"] = "ok"
    return selected, summary


def probe_wechat_group_sessions(
    config: AppConfig,
    session_probe: Callable[[AppConfig], Any] | None = None,
) -> tuple[list[SessionConfig], dict[str, Any]]:
    if session_probe is not None:
        payload = session_probe(config)
    else:
        result = run_wx_cli_json(config, ["sessions", "--json"])
        if result.status != "ok":
            return [], {
                "source_status": "failed",
                "source_error_code": clean_text(result.error_code) or result.status,
                "detected_session_count": 0,
                "detected_group_count": 0,
                "excluded_non_group_count": 0,
                "groups_returned": False,
                "session_names_returned": False,
            }
        payload = result.parsed
    if isinstance(payload, dict) and clean_text(payload.get("status")) not in {"", "ok", "success"}:
        return [], {
            "source_status": clean_text(payload.get("status")) or "failed",
            "source_error_code": clean_text(payload.get("error_code")) or "session_probe_failed",
            "detected_session_count": len(session_probe_payload_items(payload)),
            "detected_group_count": 0,
            "excluded_non_group_count": len(session_probe_payload_items(payload)),
            "groups_returned": False,
            "session_names_returned": False,
        }
    return detected_wechat_group_sessions(payload)


def upsert_detected_monitor_groups(config: AppConfig, sessions: list[SessionConfig]) -> int:
    by_id = {session.external_id: session for session in config.sessions}
    by_name = {
        session.display_name: session
        for session in config.sessions
        if local_group_display_meta(session.display_name)["status"] == "resolved"
        and clean_text(getattr(session, "display_name_status", "resolved")) != "unresolved"
    }
    inserted = 0
    updated = 0
    for detected in sessions:
        detected_meta = local_group_display_meta(detected.display_name)
        name_match = (
            by_name.get(detected.display_name)
            if detected_meta["status"] == "resolved"
            else None
        )
        existing = by_id.get(detected.external_id) or name_match
        if existing is not None:
            existing_meta = local_group_display_meta(existing.display_name)
            if (
                existing_meta["status"] == "unresolved"
                and detected_meta["status"] == "resolved"
            ):
                existing.display_name = detected.display_name
                existing.display_name_status = detected.display_name_status
                existing.display_name_source = detected.display_name_source
                existing.display_name_reason_code = detected.display_name_reason_code
                updated += 1
            continue
        config.sessions.append(detected)
        inserted += 1
    if inserted or updated:
        write_config_center_yaml(config)
    return inserted


def persistent_real_read_blocked(
    error_code: str,
    message: str,
    *,
    selected_group_count: int = 0,
    window_summary: dict[str, Any] | None = None,
    trigger: str = "manual",
    scope_mode: str = "configurable_window",
    scope_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window_summary = window_summary or {}
    scope_extra = scope_extra or {}
    return {
        "status": "blocked",
        "authorization_mode": "persistent",
        "trigger": trigger,
        "will_run": False,
        "real_read_enabled": False,
        "real_read_enabled_after": False,
        "error_code": error_code,
        "reason_code": error_code,
        "message": message,
        "scope": {
            "scope_mode": scope_mode,
            "authorization_mode": "persistent",
            "trigger": trigger,
            "selected_group_count": selected_group_count,
            "groups_returned": False,
            "session_names_returned": False,
            **window_summary,
            **scope_extra,
        },
        "limits": window_summary,
        "execution": {
            "entry_opened": False,
            "authorization_mode": "persistent",
            "persistent_authorization_enabled": False,
            "will_execute_wx_history": False,
            "will_execute_wx_search": False,
            "will_execute_wx_export": False,
            "will_execute_wx_new_messages": False,
            "no_real_read_executed": True,
            "real_read_enabled_after": False,
        },
        "execution_summary": {
            "status": "blocked",
            "error_code": error_code,
            "sessions_total": selected_group_count,
            "sessions_success": 0,
            "sessions_failed": selected_group_count,
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        },
        "failure_summary": {
            "status": "blocked",
            "error_code": error_code,
            "error_count": 1,
            "failed_group_count": selected_group_count,
            "details_returned": False,
        },
    }


def persistent_real_read_trigger(payload: dict[str, Any]) -> str:
    raw = clean_text(payload.get("trigger") or payload.get("trigger_type") or "manual")
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"schedule", "scheduled", "timer", "interval"}:
        return "scheduled"
    return "manual" if normalized in {"", "manual", "run_now", "once"} else normalized


def enabled_whitelist_sessions(config: AppConfig) -> list[SessionConfig]:
    return [
        session
        for session in config.sessions
        if session.enabled
        and session.is_whitelisted
        and not getattr(session, "archived", False)
    ]


def persistent_selected_sessions(
    config: AppConfig, payload: dict[str, Any]
) -> tuple[list[SessionConfig], int, bool]:
    enabled_whitelist = enabled_whitelist_sessions(config)
    tokens = requested_group_tokens(payload)
    include_all = parse_bool(payload.get("include_all_enabled_whitelist"), not tokens)
    if tokens and not include_all:
        token_set = set(tokens)
        selected = [
            session
            for session in enabled_whitelist
            if session.external_id in token_set or session.display_name in token_set
        ]
        return selected, len(tokens), len(selected) == len(tokens)
    return enabled_whitelist, len(enabled_whitelist), True


def persistent_real_read_run_plan(
    config: AppConfig,
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    executor: Callable[[dict[str, Any]], Any] | None = None,
    session_probe: Callable[[AppConfig], Any] | None = None,
) -> dict[str, Any]:
    trigger = persistent_real_read_trigger(payload)
    scope_mode = normalized_real_trial_scope_mode(payload)
    if scope_mode not in {"configurable_window", "all_wechat_groups"}:
        scope_mode = "configurable_window"
    if trigger not in {"manual", "scheduled"}:
        return persistent_real_read_blocked(
            "persistent_real_read_trigger_invalid",
            "长期真实读取触发方式只支持手动或定时。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if not bool(getattr(config.wx_cli, "persistent_real_read_enabled", False)):
        return persistent_real_read_blocked(
            "persistent_real_read_disabled",
            "长期真实读取授权默认关闭；未执行真实读取。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if bool(getattr(config.wx_cli, "persistent_real_read_paused", False)):
        return persistent_real_read_blocked(
            "persistent_real_read_paused",
            "长期真实读取已暂停；未执行真实读取。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    test_account_confirmed = bool(
        getattr(config.wx_cli, "persistent_real_read_test_account_confirmed", False)
    ) or parse_bool(payload.get("test_wechat_account_confirmed"), False)
    if not test_account_confirmed:
        return persistent_real_read_blocked(
            "persistent_real_read_test_account_required",
            "长期真实读取需要确认 Windows 测试微信号；未执行真实读取。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if trigger == "scheduled" and not bool(
        getattr(config.wx_cli, "persistent_real_read_schedule_enabled", False)
    ):
        return persistent_real_read_blocked(
            "persistent_real_read_schedule_disabled",
            "长期真实读取定时触发未开启；未执行真实读取。",
            trigger=trigger,
            scope_mode=scope_mode,
        )

    caps = expanded_real_trial_caps(config)
    window_payload = dict(payload)
    if (
        clean_text(window_payload.get("lookback_days")) == ""
        and clean_text(window_payload.get("start_time") or window_payload.get("start_at")) == ""
        and clean_text(window_payload.get("end_time") or window_payload.get("end_at")) == ""
    ):
        window_payload["lookback_days"] = persistent_real_read_default_lookback_days(config)
    window_summary, error_code = trial_window_summary(window_payload, caps)
    if error_code == "expanded_trial_time_range_invalid":
        return persistent_real_read_blocked(
            "expanded_trial_time_range_invalid",
            "长期真实读取起止时间必须完整且结束时间晚于开始时间。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if error_code or window_summary is None:
        return persistent_real_read_blocked(
            "expanded_trial_lookback_days_invalid",
            "长期真实读取天数必须是正整数。",
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if window_summary["effective_lookback_days"] > caps["max_allowed_lookback_days"]:
        return persistent_real_read_blocked(
            "expanded_trial_lookback_days_too_large",
            "长期真实读取范围超过当前配置上限。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )

    max_total_messages, error_code = parse_trial_int(
        payload.get("max_total_messages", payload.get("limit")),
        caps["max_total_messages"],
        "expanded_trial_total_limit_invalid",
    )
    if error_code or max_total_messages is None or max_total_messages < 1:
        return persistent_real_read_blocked(
            "expanded_trial_total_limit_invalid",
            "长期真实读取总消息上限必须是正整数。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if max_total_messages > caps["max_total_messages"]:
        return persistent_real_read_blocked(
            "expanded_trial_total_limit_too_large",
            "长期真实读取总消息上限超过安全配置。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )

    max_messages_per_group, error_code = parse_trial_int(
        payload.get("max_messages_per_group"),
        caps["max_messages_per_group"],
        "expanded_trial_group_limit_invalid",
    )
    if error_code or max_messages_per_group is None or max_messages_per_group < 1:
        return persistent_real_read_blocked(
            "expanded_trial_group_limit_invalid",
            "长期真实读取单群消息上限必须是正整数。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if max_messages_per_group > caps["max_messages_per_group"]:
        return persistent_real_read_blocked(
            "expanded_trial_group_limit_too_large",
            "长期真实读取单群消息上限超过安全配置。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )

    batch_limit, error_code = parse_trial_int(
        payload.get("batch_limit", payload.get("max_batches")),
        caps["batch_limit"],
        "expanded_trial_batch_limit_invalid",
    )
    if error_code or batch_limit is None or batch_limit < 1:
        return persistent_real_read_blocked(
            "expanded_trial_batch_limit_invalid",
            "长期真实读取批次上限必须是正整数。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if batch_limit > caps["batch_limit"]:
        return persistent_real_read_blocked(
            "expanded_trial_batch_limit_too_large",
            "长期真实读取批次上限超过安全配置。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )

    scope_summary: dict[str, Any] = {}
    local_groups_upserted = 0
    if scope_mode == "all_wechat_groups":
        selected_sessions, scope_summary = probe_wechat_group_sessions(config, session_probe)
        if scope_summary.get("source_status") not in {"ok", "success"}:
            return persistent_real_read_blocked(
                "persistent_real_read_session_probe_failed",
                "全部微信群范围需要先完成会话探针；未执行消息读取。",
                selected_group_count=0,
                window_summary=window_summary,
                trigger=trigger,
                scope_mode=scope_mode,
                scope_extra=scope_summary,
            )
        local_groups_upserted = upsert_detected_monitor_groups(config, selected_sessions)
        requested_group_count = int(scope_summary.get("detected_group_count") or 0)
        scope_valid = True
    else:
        selected_sessions, requested_group_count, scope_valid = persistent_selected_sessions(
            config, payload
        )
    selected_group_count = len(selected_sessions)
    if not scope_valid:
        return persistent_real_read_blocked(
            "persistent_real_read_group_scope_invalid",
            "长期真实读取只能读取已启用白名单监控群。",
            selected_group_count=selected_group_count,
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
        )
    if selected_group_count < 1:
        return persistent_real_read_blocked(
            "expanded_trial_no_groups_selected",
            "没有可用于长期真实读取的微信群。",
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
            scope_extra=scope_summary,
        )
    if selected_group_count > caps["max_groups"]:
        return persistent_real_read_blocked(
            "expanded_trial_group_count_too_large",
            "长期真实读取群数量超过安全配置。",
            selected_group_count=selected_group_count,
            window_summary=window_summary,
            trigger=trigger,
            scope_mode=scope_mode,
            scope_extra=scope_summary,
        )

    limits_summary = {
        **window_summary,
        "max_groups": caps["max_groups"],
        "max_total_messages": caps["max_total_messages"],
        "requested_total_messages": max_total_messages,
        "max_messages_per_group": caps["max_messages_per_group"],
        "requested_messages_per_group": max_messages_per_group,
        "batch_limit": caps["batch_limit"],
        "requested_batch_limit": batch_limit,
    }
    if executor is not None:
        execution_result = execution_summary_from_result(
            executor(
                {
                    "authorization_mode": "persistent",
                    "trigger": trigger,
                    "scope_mode": scope_mode,
                    "selected_group_count": selected_group_count,
                    **scope_summary,
                    "window": dict(window_summary),
                    "limits": dict(limits_summary),
                    "real_read_enabled_before": bool(config.wx_cli.real_read_enabled),
                }
            )
        )
    else:
        real_read_before = bool(config.wx_cli.real_read_enabled)
        try:
            config.wx_cli.real_read_enabled = True
            execution_result = execute_configurable_real_trial_once(
                config,
                conn,
                selected_sessions,
                window_summary,
                limits_summary,
                collection_mode="persistent_real_read",
            )
        finally:
            config.wx_cli.real_read_enabled = False
            if real_read_before and conn is None:
                config.wx_cli.real_read_enabled = False

    failure_summary = {
        "status": execution_result["status"],
        "error_code": execution_result["error_code"],
        "error_count": 1 if execution_result["error_code"] else 0,
        "failed_group_count": execution_result["sessions_failed"],
        "details_returned": False,
    }
    return {
        "status": execution_result["status"],
        "authorization_mode": "persistent",
        "trigger": trigger,
        "will_run": True,
        "real_read_enabled": False,
        "real_read_enabled_after": False,
        "error_code": execution_result["error_code"],
        "reason_code": execution_result["error_code"],
        "message": "长期真实读取已通过授权配置进入执行路径；响应仅返回数量和状态摘要。",
        "scope": {
            "scope_mode": scope_mode,
            "authorization_mode": "persistent",
            "trigger": trigger,
            "multi_group": True,
            "lookback_days": window_summary["effective_lookback_days"],
            "enabled_whitelist_count": len(enabled_whitelist_sessions(config)),
            "requested_group_count": requested_group_count,
            "selected_group_count": selected_group_count,
            "local_monitor_groups_upserted": local_groups_upserted,
            "test_wechat_account_confirmed": True,
            "groups_returned": False,
            "session_names_returned": False,
            "no_external_send": True,
            "no_auto_reply": True,
            "no_formal_write": True,
            **window_summary,
            **scope_summary,
        },
        "limits": limits_summary,
        "execution": {
            "entry_opened": True,
            "authorization_mode": "persistent",
            "persistent_authorization_enabled": True,
            "will_execute_wx_history": True,
            "will_execute_wx_search": False,
            "will_execute_wx_export": False,
            "will_execute_wx_new_messages": False,
            "no_real_read_executed": False,
            "real_read_enabled_after": False,
            "writes_local_raw_normalized_candidate": True,
        },
        "execution_summary": execution_result,
        "failure_summary": failure_summary,
    }


def persistent_real_read_control_payload(
    config: AppConfig,
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    action = clean_text(payload.get("action")).lower().replace("-", "_")
    if action in {"pause", "paused"}:
        config.wx_cli.persistent_real_read_paused = True
        status = "paused"
    elif action in {"resume", "resumed"}:
        config.wx_cli.persistent_real_read_paused = False
        status = "resumed"
    elif action in {"enable", "enabled"}:
        config.wx_cli.persistent_real_read_enabled = True
        config.wx_cli.persistent_real_read_paused = False
        config.wx_cli.persistent_real_read_test_account_confirmed = parse_bool(
            payload.get("test_account_confirmed"),
            bool(
                getattr(
                    config.wx_cli,
                    "persistent_real_read_test_account_confirmed",
                    False,
                )
            ),
        )
        status = "enabled"
    elif action in {"disable", "disabled"}:
        config.wx_cli.persistent_real_read_enabled = False
        config.wx_cli.persistent_real_read_paused = False
        status = "disabled"
    else:
        return {
            "status": "blocked",
            "error_code": "persistent_real_read_control_action_invalid",
            "persistent_authorization": persistent_real_read_contract_payload(config),
            "real_read_enabled_after": False,
        }
    config.wx_cli.real_read_enabled = False
    write_config_center_yaml(config)
    return {
        "status": status,
        "error_code": "",
        "persistent_authorization": persistent_real_read_contract_payload(config),
        "save_target": "config/app.yaml",
        "triggers_collection": False,
        "real_read_enabled_after": False,
        "formal_write_enabled": False,
    }


def expanded_real_trial_run_plan(
    config: AppConfig,
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    executor: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    if not parse_bool(payload.get("confirmed"), False):
        return {
            "status": "needs_confirmation",
            "will_run": False,
            "real_read_enabled": False,
            "error_code": "confirmation_required",
            "message": "扩大试验前需要确认范围、授权字段和禁止项。",
            "scope": {
                "scope_mode": "configurable_window",
                "groups_returned": False,
                "session_names_returned": False,
            },
            "failure_summary": {
                "status": "blocked",
                "error_code": "confirmation_required",
                "error_count": 1,
                "failed_group_count": 0,
                "details_returned": False,
            },
        }

    authorization_confirmed = any(
        parse_bool(payload.get(key), False)
        for key in (
            "authorize_expanded_real_read_trial",
            "expanded_trial_authorized",
            "authorization_confirmed",
        )
    )
    if not authorization_confirmed:
        return expanded_trial_blocked(
            "expanded_trial_authorization_required",
            "可配置时间窗口真实读取扩大试验需要单独授权；本接口未执行读取。",
        )

    test_account_confirmed = any(
        parse_bool(payload.get(key), False)
        for key in (
            "test_wechat_account_confirmed",
            "test_account_confirmed",
            "test_wechat_account_configured",
        )
    )
    if not test_account_confirmed:
        return expanded_trial_blocked(
            "expanded_trial_test_account_required",
            "扩大试验需要确认使用测试微信号，不会默认使用本机配置。",
        )

    one_time_confirmed = any(
        parse_bool(payload.get(key), False)
        for key in ("one_time_expanded_trial", "one_time_trial", "one_time")
    )
    if not one_time_confirmed:
        return expanded_trial_blocked(
            "expanded_trial_one_time_required",
            "扩大试验必须声明为一次性试验，不能自动定时采集。",
        )

    caps = expanded_real_trial_caps(config)
    window_summary, error_code = trial_window_summary(payload, caps)
    if error_code == "expanded_trial_time_range_invalid":
        return expanded_trial_blocked(
            "expanded_trial_time_range_invalid",
            "扩大试验起止时间必须完整且结束时间晚于开始时间。",
        )
    if error_code or window_summary is None:
        return expanded_trial_blocked(
            "expanded_trial_lookback_days_invalid",
            "扩大试验天数必须是正整数。",
        )
    if window_summary["effective_lookback_days"] > caps["max_allowed_lookback_days"]:
        return expanded_trial_blocked(
            "expanded_trial_lookback_days_too_large",
            "扩大试验范围超过当前配置上限。",
            window_summary=window_summary,
        )

    max_total_messages, error_code = parse_trial_int(
        payload.get("max_total_messages", payload.get("limit")),
        caps["max_total_messages"],
        "expanded_trial_total_limit_invalid",
    )
    if error_code or max_total_messages is None or max_total_messages < 1:
        return expanded_trial_blocked(
            "expanded_trial_total_limit_invalid",
            "扩大试验总消息上限必须是正整数。",
        )
    if max_total_messages > caps["max_total_messages"]:
        return expanded_trial_blocked(
            "expanded_trial_total_limit_too_large",
            "扩大试验总消息上限超过安全配置。",
        )

    max_messages_per_group, error_code = parse_trial_int(
        payload.get("max_messages_per_group"),
        caps["max_messages_per_group"],
        "expanded_trial_group_limit_invalid",
    )
    if error_code or max_messages_per_group is None or max_messages_per_group < 1:
        return expanded_trial_blocked(
            "expanded_trial_group_limit_invalid",
            "扩大试验单群消息上限必须是正整数。",
        )
    if max_messages_per_group > caps["max_messages_per_group"]:
        return expanded_trial_blocked(
            "expanded_trial_group_limit_too_large",
            "扩大试验单群消息上限超过安全配置。",
        )

    batch_limit, error_code = parse_trial_int(
        payload.get("batch_limit", payload.get("max_batches")),
        caps["batch_limit"],
        "expanded_trial_batch_limit_invalid",
    )
    if error_code or batch_limit is None or batch_limit < 1:
        return expanded_trial_blocked(
            "expanded_trial_batch_limit_invalid",
            "扩大试验批次上限必须是正整数。",
        )
    if batch_limit > caps["batch_limit"]:
        return expanded_trial_blocked(
            "expanded_trial_batch_limit_too_large",
            "扩大试验批次上限超过安全配置。",
        )

    enabled_whitelist = [
        session
        for session in config.sessions
        if session.enabled and session.is_whitelisted and not getattr(session, "archived", False)
    ]
    tokens = requested_group_tokens(payload)
    include_all_enabled = parse_bool(payload.get("include_all_enabled_whitelist"), False)
    if tokens and not include_all_enabled:
        token_set = set(tokens)
        selected_sessions = [
            session
            for session in enabled_whitelist
            if session.external_id in token_set or session.display_name in token_set
        ]
        requested_group_count = len(tokens)
    else:
        selected_sessions = enabled_whitelist
        requested_group_count = len(enabled_whitelist)

    selected_group_count = len(selected_sessions)
    if selected_group_count < 1:
        return expanded_trial_blocked(
            "expanded_trial_no_groups_selected",
            "没有可用于扩大试验的启用白名单群。",
        )
    if selected_group_count > caps["max_groups"]:
        return expanded_trial_blocked(
            "expanded_trial_group_count_too_large",
            "扩大试验群数量超过安全配置。",
            selected_group_count=selected_group_count,
        )

    limits_summary = {
        **window_summary,
        "max_groups": caps["max_groups"],
        "max_total_messages": caps["max_total_messages"],
        "requested_total_messages": max_total_messages,
        "max_messages_per_group": caps["max_messages_per_group"],
        "requested_messages_per_group": max_messages_per_group,
        "batch_limit": caps["batch_limit"],
        "requested_batch_limit": batch_limit,
    }
    should_execute = execution_requested(payload)
    if should_execute and not one_time_authorization_present(payload):
        return expanded_trial_blocked(
            "one_time_authorization_token_required",
            "一次性真实试验执行需要授权令牌或等价授权标记。",
            selected_group_count=selected_group_count,
            window_summary=window_summary,
        )

    execution_result: dict[str, Any] | None = None
    if should_execute:
        if executor is not None:
            execution_result = execution_summary_from_result(
                executor(
                    {
                        "selected_group_count": selected_group_count,
                        "window": dict(window_summary),
                        "limits": dict(limits_summary),
                        "real_read_enabled_before": bool(config.wx_cli.real_read_enabled),
                    }
                )
            )
        else:
            real_read_before = bool(config.wx_cli.real_read_enabled)
            try:
                config.wx_cli.real_read_enabled = True
                execution_result = execute_configurable_real_trial_once(
                    config,
                    conn,
                    selected_sessions,
                    window_summary,
                    limits_summary,
                )
            finally:
                config.wx_cli.real_read_enabled = False
                if real_read_before and conn is None:
                    config.wx_cli.real_read_enabled = False

    status = "dry_run_ready"
    error_code = "real_trial_execution_entry_not_opened"
    reason_code = "real_trial_execution_entry_not_opened"
    message = "扩大试验计划已生成；未打开一次性执行入口，未执行真实读取。"
    failure_summary = {
        "status": "not_executed",
        "error_code": "real_trial_execution_entry_not_opened",
        "error_count": 0,
        "failed_group_count": 0,
        "details_returned": False,
    }
    if execution_result is not None:
        status = execution_result["status"]
        error_code = execution_result["error_code"]
        reason_code = error_code
        message = "一次性真实试验执行路径已进入；响应仅返回数量和状态摘要。"
        failure_summary = {
            "status": execution_result["status"],
            "error_code": execution_result["error_code"],
            "error_count": 1 if execution_result["error_code"] else 0,
            "failed_group_count": execution_result["sessions_failed"],
            "details_returned": False,
        }

    return {
        "status": status,
        "will_run": bool(should_execute),
        "real_read_enabled": False,
        "real_read_enabled_after": False,
        "error_code": error_code,
        "reason_code": reason_code,
        "message": message,
        "scope": {
            "scope_mode": "configurable_window",
            "preset": "last_30_days"
            if window_summary["effective_lookback_days"] == 30
            else "custom_window",
            "one_time_expanded_trial": True,
            "multi_group": True,
            "lookback_days": window_summary["effective_lookback_days"],
            "enabled_whitelist_count": len(enabled_whitelist),
            "requested_group_count": requested_group_count,
            "selected_group_count": selected_group_count,
            "test_wechat_account_confirmed": True,
            "groups_returned": False,
            "session_names_returned": False,
            "no_external_send": True,
            "no_auto_reply": True,
            "no_formal_write": True,
            "no_auto_schedule": True,
            "authorization_marker_present": True,
            **window_summary,
        },
        "limits": limits_summary,
        "execution": {
            "entry_opened": bool(should_execute),
            "will_execute_wx_history": bool(should_execute),
            "will_execute_wx_search": False,
            "will_execute_wx_export": False,
            "will_execute_wx_new_messages": False,
            "no_real_read_executed": not bool(should_execute),
            "requires_runtime_authorization": True,
            "one_time_authorization_present": bool(should_execute),
            "real_read_enabled_after": False,
        },
        "execution_summary": execution_result
        or {
            "status": "not_executed",
            "error_code": "real_trial_execution_entry_not_opened",
            "sessions_total": selected_group_count,
            "sessions_success": 0,
            "sessions_failed": 0,
            "raw_messages_seen": 0,
            "raw_messages_inserted": 0,
            "raw_messages_duplicated": 0,
            "candidate_items_created": 0,
            "candidate_items_updated": 0,
        },
        "failure_summary": failure_summary,
    }


def real_trial_run_plan(
    config: AppConfig,
    payload: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    executor: Callable[[dict[str, Any]], Any] | None = None,
    session_probe: Callable[[AppConfig], Any] | None = None,
) -> dict[str, Any]:
    scope_mode = normalized_real_trial_scope_mode(payload)
    if scope_mode in {"configurable_window", "all_wechat_groups"}:
        if normalized_authorization_mode(payload) == "persistent":
            return persistent_real_read_run_plan(
                config,
                payload,
                conn=conn,
                executor=executor,
                session_probe=session_probe,
            )
        if scope_mode == "all_wechat_groups":
            return expanded_trial_blocked(
                "all_wechat_groups_requires_persistent_authorization",
                "全部微信群首跑范围只允许通过长期真实读取授权契约进入。",
            )
        return expanded_real_trial_run_plan(
            config,
            payload,
            conn=conn,
            executor=executor,
        )

    confirmed = bool(payload.get("confirmed", False))
    limit = clamp_int(
        payload.get("limit"),
        minimum=1,
        maximum=LEGACY_REAL_TRIAL_MAX_LIMIT,
        default=LEGACY_REAL_TRIAL_MAX_LIMIT,
    )
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
    if requested_limit > LEGACY_REAL_TRIAL_MAX_LIMIT:
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
        "real_read_enabled": False,
        "error_code": "real_trial_run_not_executed_in_this_task",
        "message": "安全检查通过；本轮开发只提供安全壳，未执行真实读取。",
        "scope": {
            "scope_mode": "legacy_recent50",
            "enabled_whitelist_count": 1,
            "limit": limit,
            "preset": preset,
            "start_at": start_at,
            "end_at": end_at,
            "lookback_hours": lookback_raw,
            "groups_returned": False,
            "session_names_returned": False,
            "no_external_send": True,
            "no_auto_reply": True,
            "no_formal_write": True,
        },
        "failure_summary": {
            "status": "not_executed",
            "error_code": "real_trial_run_not_executed_in_this_task",
            "error_count": 0,
            "failed_group_count": 0,
            "details_returned": False,
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
            "real_lookback_hours": min(
                max(1, int(config.wx_cli.real_lookback_hours)),
                LEGACY_REAL_TRIAL_MAX_LOOKBACK_HOURS,
            ),
            "real_limit": min(
                max(1, int(config.wx_cli.real_limit)),
                LEGACY_REAL_TRIAL_MAX_LIMIT,
            ),
            "real_start_at": config.wx_cli.real_start_at,
            "real_end_at": config.wx_cli.real_end_at,
            "expanded_real_lookback_days": expanded_real_trial_caps(config)[
                "max_allowed_lookback_days"
            ],
            "expanded_real_max_groups": expanded_real_trial_caps(config)["max_groups"],
            "expanded_real_max_total_messages": expanded_real_trial_caps(config)[
                "max_total_messages"
            ],
            "expanded_real_max_messages_per_group": expanded_real_trial_caps(config)[
                "max_messages_per_group"
            ],
            "expanded_real_batch_limit": expanded_real_trial_caps(config)[
                "batch_limit"
            ],
            "persistent_real_read_enabled": bool(
                getattr(config.wx_cli, "persistent_real_read_enabled", False)
            ),
            "persistent_real_read_paused": bool(
                getattr(config.wx_cli, "persistent_real_read_paused", False)
            ),
            "persistent_real_read_test_account_confirmed": bool(
                getattr(config.wx_cli, "persistent_real_read_test_account_confirmed", False)
            ),
            "persistent_real_read_schedule_enabled": bool(
                getattr(config.wx_cli, "persistent_real_read_schedule_enabled", False)
            ),
            "persistent_real_read_interval_minutes": persistent_real_read_interval_minutes(
                config
            ),
            "persistent_real_read_default_lookback_days": persistent_real_read_default_lookback_days(
                config
            ),
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
                "display_name_status": getattr(
                    session,
                    "display_name_status",
                    local_group_display_meta(session.display_name)["status"],
                ),
                "display_name_source": getattr(session, "display_name_source", ""),
                "display_name_reason_code": getattr(
                    session,
                    "display_name_reason_code",
                    local_group_display_meta(session.display_name)["reason_code"],
                ),
                "customer_name": session.customer_name,
                "channel_name": session.channel_name,
                "module_name": session.module_name,
                "owner_name": primary_owner_name(session),
                "owner_names": normalized_owner_names(session),
                "customer_stage": session.customer_stage,
                "group_type": session.group_type,
                "common_contacts": list(session.common_contacts),
                "reply_notes": session.reply_notes,
                "is_whitelisted": bool(session.is_whitelisted),
                "enabled": bool(session.enabled),
                "verification_status": safe_verification_status(
                    session.verification_status
                ),
                "daily_monitor_enabled": bool(session.daily_monitor_enabled),
                "include_in_daily": bool(session.include_in_daily),
                "trial_scope": session.trial_scope,
                "internal_people": list(session.internal_people),
                "roster_member_names": list(
                    getattr(session, "roster_member_names", []) or []
                ),
                "archived": bool(getattr(session, "archived", False)),
            }
            for session in config.sessions
        ],
        "internal_people": [
            {
                "person_name": person.person_name,
                "wechat_display_name": person.wechat_display_name,
                "aliases": list(person.aliases),
                "role": person.role,
                "modules": list(person.modules),
                "enabled": bool(person.enabled),
                "notes": getattr(person, "notes", ""),
            }
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


def local_ui_display_text(value: Any) -> str:
    """Keep local UI labels readable while still blocking hard-forbidden tokens."""
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"(?i)wxid[_a-z0-9-]*", "[敏感信息已脱敏]", text)
    text = re.sub(r"(?i)secret[_a-z0-9-]*", "[敏感信息已脱敏]", text)
    text = re.sub(
        r"(?i)(key|salt|daemon|raw_payload_json|raw_payload|content_text)",
        "[敏感信息已脱敏]",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Z]:\\(?:[^\\\s|，。；,;]+\\)*[^\\\s|，。；,;]+",
        "[路径已脱敏]",
        text,
    )
    text = re.sub(
        r"/(?:Users|private|var|tmp|Applications|Volumes)(?:/[^\s|，。；,;]+)+",
        "[路径已脱敏]",
        text,
    )
    text = re.sub(
        r"(?:^|\s)(?:微信agent专项|data|exports|config|logs)(?:/[^\s|，。；,;]+)+",
        " [路径已脱敏]",
        text,
    )
    return text.strip()


def local_ui_display_list(values: list[Any]) -> list[str]:
    return unique_clean_text([local_ui_display_text(value) for value in values])


def is_internal_identifier_for_display(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return True
    if text == GROUP_DISPLAY_PLACEHOLDER:
        return True
    lowered = text.lower()
    if "@chatroom" in lowered:
        return True
    if lowered.startswith("wxid_") or lowered.startswith("gh_"):
        return True
    if lowered in {"filehelper", "文件传输助手"}:
        return True
    if any(token in lowered for token in ("key", "salt", "daemon", "raw_payload")):
        return True
    if re.search(r"(?i)\b[A-Z]:\\", text) or re.search(
        r"/(?:Users|private|var|tmp|Applications|Volumes)/", text
    ):
        return True
    if re.fullmatch(r"\d{6,}", text):
        return True
    if re.fullmatch(r"[a-f0-9]{12,64}", lowered):
        return True
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{13,}", lowered):
        return True
    if re.fullmatch(r"(?:detected-wechat-group|local-monitor)-[a-f0-9]{8,}", lowered):
        return True
    return False


def local_group_display_meta(value: Any, *, source: str = "config_display_name") -> dict[str, str]:
    raw = clean_text(value)
    display = local_ui_display_text(raw)
    if not raw:
        return {
            "value": GROUP_DISPLAY_PLACEHOLDER,
            "status": "unresolved",
            "reason_code": "empty_display_name",
            "source_error_code": "group_display_name_unresolved",
            "source": source,
        }
    if (
        is_internal_identifier_for_display(raw)
        or is_internal_identifier_for_display(display)
        or "[敏感信息已脱敏]" in display
        or "[路径已脱敏]" in display
    ):
        return {
            "value": GROUP_DISPLAY_PLACEHOLDER,
            "status": "unresolved",
            "reason_code": "internal_identifier_only",
            "source_error_code": "group_display_name_unresolved",
            "source": source,
        }
    return {
        "value": display,
        "status": "resolved",
        "reason_code": "",
        "source_error_code": "",
        "source": source,
    }


def local_group_display_fields(value: Any, *, source: str = "config_display_name") -> dict[str, str]:
    meta = local_group_display_meta(value, source=source)
    return {
        "group_label": meta["value"],
        "group_label_safe": redact_visible_text(meta["value"]),
        "group_label_status": meta["status"],
        "group_label_reason_code": meta["reason_code"],
        "group_label_source_error_code": meta["source_error_code"],
    }


def now_local_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def primary_owner_from_payload(item: dict[str, Any]) -> str:
    owner_names = clean_text_list(item.get("owner_names", item.get("owner_name")))
    return owner_names[0] if owner_names else ""


def clean_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("，", ",").replace("\r", "\n").replace(",", "\n").split("\n")
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


def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    clamped = min(max(number, minimum), maximum)
    return int(clamped) if float(clamped).is_integer() else clamped


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
