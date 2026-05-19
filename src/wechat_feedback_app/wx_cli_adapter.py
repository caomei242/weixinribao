from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig, SessionConfig, TRIAL_SESSION_NAME, resolve_path

MAX_REAL_LOOKBACK_HOURS = 2
MAX_REAL_LIMIT = 50


class WxCliUnavailable(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class NormalizedMessage:
    session_external_id: str
    session_name: str
    message_external_id: str | None
    local_id: str | None
    sender_display_name: str
    sender_raw_id: str | None
    sent_at: str
    message_type: str
    content_text: str
    raw_payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_external_id": self.session_external_id,
            "session_name": self.session_name,
            "message_external_id": self.message_external_id,
            "local_id": self.local_id,
            "sender_display_name": self.sender_display_name,
            "sender_raw_id": self.sender_raw_id,
            "sent_at": self.sent_at,
            "message_type": self.message_type,
            "content_text": self.content_text,
            "raw_payload": self.raw_payload,
        }


@dataclass
class WxCliCommandResult:
    status: str
    message: str
    command: str
    returncode: int | None = None
    parsed: Any = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    binary_path: str = ""


def fetch_messages(
    config: AppConfig, now: datetime | None = None
) -> list[NormalizedMessage]:
    if config.wx_cli.mode == "fixture":
        return fetch_fixture_messages(config)
    if config.wx_cli.mode == "real":
        return fetch_real_trial_messages(config, now=now)
    raise WxCliUnavailable("invalid_mode", f"未知 wx_cli.mode: {config.wx_cli.mode}")


def fetch_fixture_messages(config: AppConfig) -> list[NormalizedMessage]:
    fixture_dir = resolve_path(config.root, config.wx_cli.fixture_dir)
    fixture_path = fixture_dir / "wx_messages.sample.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    messages: list[NormalizedMessage] = []
    for item in payload.get("messages", []):
        raw_payload = dict(item)
        messages.append(
            NormalizedMessage(
                session_external_id=str(item["session_external_id"]),
                session_name=str(item.get("session_name", "")),
                message_external_id=item.get("message_external_id"),
                local_id=item.get("local_id"),
                sender_display_name=str(item.get("sender_display_name", "")),
                sender_raw_id=item.get("sender_raw_id"),
                sent_at=str(item["sent_at"]),
                message_type=str(item.get("message_type", "text")),
                content_text=str(item.get("content_text", "")),
                raw_payload=raw_payload,
            )
        )
    return messages


def fetch_real_trial_messages(
    config: AppConfig, now: datetime | None = None
) -> list[NormalizedMessage]:
    if not config.wx_cli.real_read_enabled:
        raise WxCliUnavailable(
            "real_read_disabled",
            "真实消息读取开关未开启；不会执行 wx history。",
        )

    connection = test_connection(config)
    if connection["status"] != "ok":
        raise WxCliUnavailable(connection["status"], connection["message"])

    session = find_trial_session(config)
    result = run_wx_cli_json(config, build_history_args(config, now=now))
    if result.status != "ok":
        raise WxCliUnavailable(result.status, safe_history_error_message(result.status))
    return map_history_payload(result.parsed, session)


def find_trial_session(config: AppConfig) -> SessionConfig:
    configured = config.wx_cli.real_allowed_session.strip()
    if configured != TRIAL_SESSION_NAME:
        raise WxCliUnavailable(
            "real_trial_session_not_allowed",
            "真实读取试点只允许指定单一会话。",
        )

    enabled_whitelist = [
        session
        for session in config.sessions
        if session.enabled and session.is_whitelisted
    ]
    if len(enabled_whitelist) != 1:
        raise WxCliUnavailable(
            "real_trial_whitelist_count_invalid",
            "真实读取试点要求启用白名单会话数量必须等于 1。",
        )

    session = enabled_whitelist[0]
    if session.display_name == TRIAL_SESSION_NAME or session.external_id == TRIAL_SESSION_NAME:
        return session

    raise WxCliUnavailable(
        "real_trial_session_not_whitelisted",
        "指定试点会话未在启用的白名单会话中。",
    )


def build_history_args(
    config: AppConfig, now: datetime | None = None
) -> list[str]:
    hours = min(
        max(1, int(config.wx_cli.real_lookback_hours)),
        MAX_REAL_LOOKBACK_HOURS,
    )
    limit = min(max(1, int(config.wx_cli.real_limit)), MAX_REAL_LIMIT)
    current = now or datetime.now().astimezone()
    since = current - timedelta(hours=hours)
    since_text = since.strftime("%Y-%m-%d %H:%M")
    return [
        "history",
        TRIAL_SESSION_NAME,
        "--since",
        since_text,
        "-n",
        str(limit),
        "--json",
    ]


def map_history_payload(payload: Any, session: SessionConfig) -> list[NormalizedMessage]:
    messages: list[NormalizedMessage] = []
    for item in history_items(payload):
        if not isinstance(item, dict):
            continue
        chat = first_text(item, ["chat", "session", "session_name", "room_name", "name"])
        if chat and chat not in {TRIAL_SESSION_NAME, session.display_name, session.external_id}:
            continue
        content = first_text(item, ["content_text", "content", "text", "message"]) or ""
        sent_at = normalize_timestamp(
            item.get("sent_at")
            or item.get("timestamp")
            or item.get("time")
            or item.get("create_time")
        )
        messages.append(
            NormalizedMessage(
                session_external_id=session.external_id,
                session_name=session.display_name,
                message_external_id=first_text(
                    item, ["message_external_id", "message_id", "msg_id", "id"]
                ),
                local_id=first_text(item, ["local_id", "localId"]),
                sender_display_name=first_text(
                    item,
                    ["sender_display_name", "sender", "sender_name", "from", "from_name"],
                )
                or "未知",
                sender_raw_id=first_text(item, ["sender_raw_id", "sender_id", "wxid", "from_id"]),
                sent_at=sent_at,
                message_type=first_text(item, ["message_type", "type"]) or "text",
                content_text=content,
                raw_payload=dict(item),
            )
        )
    return messages


def history_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("messages", "data", "items", "history"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload] if payload else []
    return []


def first_text(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return None


def normalize_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone().isoformat()
    if value is None:
        return datetime.now().astimezone().isoformat(timespec="seconds")
    return str(value)


def safe_history_error_message(status: str) -> str:
    return {
        "missing_binary": "找不到 wx-cli 二进制；未执行真实读取。",
        "not_initialized": "wx-cli 尚未初始化；未保存任何真实消息。",
        "wechat_not_running": "微信未运行、未登录或本地数据不可读；未保存任何真实消息。",
        "permission_denied": "权限不足；未保存任何真实消息。",
        "parse_error": "wx history 输出不可解析；未保存任何真实消息。",
        "timeout": "wx history 命令超时；未保存任何真实消息。",
    }.get(status, "wx history 执行失败；未保存任何真实消息。")


def test_connection(config: AppConfig) -> dict[str, str]:
    readiness = wx_cli_readiness(config)
    if config.wx_cli.mode == "fixture":
        fixture_path = (
            resolve_path(config.root, config.wx_cli.fixture_dir)
            / "wx_messages.sample.json"
        )
        if fixture_path.exists():
            return {
                "status": "ok",
                "error_code": "",
                "message": "fixture 文件可读取",
                "wx_cli_status": readiness["status"],
                "binary_path": readiness["binary_path"],
                "configured_binary": readiness["configured_binary"],
                "binary_configured": readiness["binary_configured"],
                "is_executable": readiness["is_executable"],
                "session_count": "0",
                "next_action": readiness["next_action"],
            }
        return {
            "status": "missing_fixture",
            "error_code": "missing_fixture",
            "message": "fixture 文件不存在",
            "wx_cli_status": readiness["status"],
            "binary_path": readiness["binary_path"],
            "configured_binary": readiness["configured_binary"],
            "binary_configured": readiness["binary_configured"],
            "is_executable": readiness["is_executable"],
            "session_count": "0",
            "next_action": readiness["next_action"],
        }
    if config.wx_cli.mode != "real":
        return {
            "status": "invalid_mode",
            "error_code": "invalid_mode",
            "message": f"未知 wx_cli.mode: {config.wx_cli.mode}",
            "session_count": "0",
        }
    if readiness["status"] != "ok":
        return {
            "status": readiness["status"],
            "error_code": readiness["status"],
            "message": safe_connection_message(readiness["status"]),
            "command": "sessions --json",
            "returncode": "",
            "binary_path": readiness["binary_path"],
            "configured_binary": readiness["configured_binary"],
            "binary_configured": readiness["binary_configured"],
            "is_executable": readiness["is_executable"],
            "session_count": "0",
            "next_action": readiness["next_action"],
        }

    result = run_wx_cli_json(config, ["sessions", "--json"])
    payload = result.parsed
    session_count = count_sessions(payload) if result.status == "ok" else 0
    return {
        "status": result.status,
        "error_code": "" if result.status == "ok" else result.status,
        "message": safe_connection_message(result.status, session_count),
        "command": result.command,
        "returncode": "" if result.returncode is None else str(result.returncode),
        "binary_path": result.binary_path,
        "configured_binary": readiness["configured_binary"],
        "binary_configured": readiness["binary_configured"],
        "is_executable": readiness["is_executable"],
        "session_count": str(session_count),
        "next_action": next_action_for_status(result.status),
    }


def wx_cli_readiness(config: AppConfig) -> dict[str, str]:
    configured = config.wx_cli.binary.strip()
    if not configured:
        return {
            "status": "missing_binary",
            "message": "未配置 wx-cli 二进制路径。",
            "configured_binary": "",
            "binary_configured": "false",
            "binary_path": "",
            "is_executable": "false",
            "next_action": next_action_for_status("missing_binary"),
        }

    resolved = resolve_binary(config)
    if resolved is None:
        return {
            "status": "missing_binary",
            "message": f"找不到 wx-cli 二进制：{configured}",
            "configured_binary": configured,
            "binary_configured": "true",
            "binary_path": "",
            "is_executable": "false",
            "next_action": next_action_for_status("missing_binary"),
        }
    if not os.access(resolved, os.X_OK):
        return {
            "status": "permission_denied",
            "message": f"wx-cli 不可执行：{resolved}",
            "configured_binary": configured,
            "binary_configured": "true",
            "binary_path": resolved,
            "is_executable": "false",
            "next_action": next_action_for_status("permission_denied"),
        }
    return {
        "status": "ok",
        "message": "wx-cli 二进制可执行。",
        "configured_binary": configured,
        "binary_configured": "true",
        "binary_path": resolved,
        "is_executable": "true",
        "next_action": next_action_for_status("ok"),
    }


def run_wx_cli_json(config: AppConfig, args: list[str]) -> WxCliCommandResult:
    binary_path = resolve_binary(config)
    command_display = " ".join(args)
    if binary_path is None:
        return WxCliCommandResult(
            status="missing_binary",
            message=f"找不到 wx-cli 二进制：{config.wx_cli.binary}",
            command=command_display,
            binary_path="",
        )

    full_command = [binary_path, *args]
    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(config.wx_cli.timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return WxCliCommandResult(
            status="timeout",
            message=f"wx-cli 命令超时：{command_display}",
            command=command_display,
            returncode=None,
            stdout_preview=preview(exc.stdout),
            stderr_preview=preview(exc.stderr),
            binary_path=binary_path,
        )
    except PermissionError as exc:
        return WxCliCommandResult(
            status="permission_denied",
            message=f"wx-cli 无执行权限：{exc}",
            command=command_display,
            returncode=None,
            binary_path=binary_path,
        )
    except OSError as exc:
        return WxCliCommandResult(
            status="missing_binary",
            message=f"无法执行 wx-cli：{exc}",
            command=command_display,
            returncode=None,
            binary_path=binary_path,
        )

    stdout_preview = preview(completed.stdout)
    stderr_preview = preview(completed.stderr)
    if completed.returncode != 0:
        status = classify_error(completed.stderr, completed.stdout)
        return WxCliCommandResult(
            status=status,
            message=message_for_status(status, completed.stderr or completed.stdout),
            command=command_display,
            returncode=completed.returncode,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            binary_path=binary_path,
        )

    parsed = parse_structured_output(completed.stdout)
    if parsed is None:
        return WxCliCommandResult(
            status="parse_error",
            message="wx-cli 输出不是可解析的 JSON/YAML。",
            command=command_display,
            returncode=completed.returncode,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            binary_path=binary_path,
        )

    return WxCliCommandResult(
        status="ok",
        message="wx-cli 连接测试成功。",
        command=command_display,
        returncode=completed.returncode,
        parsed=parsed,
        stdout_preview=stdout_preview,
        stderr_preview=stderr_preview,
        binary_path=binary_path,
    )


def resolve_binary(config: AppConfig) -> str | None:
    binary = config.wx_cli.binary.strip()
    if not binary:
        return None
    path = Path(binary)
    if path.is_absolute() or path.parent != Path("."):
        return str(path) if path.exists() else None
    return shutil.which(binary)


def parse_structured_output(output: str) -> Any:
    text = output.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text)
        return parsed if isinstance(parsed, (dict, list)) else None
    except Exception:
        return None


def classify_error(stderr: str | None, stdout: str | None = None) -> str:
    text = f"{stderr or ''}\n{stdout or ''}".lower()
    if "permission" in text or "denied" in text or "access" in text:
        return "permission_denied"
    if "not initialized" in text or "uninitialized" in text or "init" in text and "config" in text:
        return "not_initialized"
    if (
        "wechat not running" in text
        or "wechat is not running" in text
        or "not logged in" in text
        or "login" in text
        or "process not found" in text
    ):
        return "wechat_not_running"
    return "parse_error"


def message_for_status(status: str, raw_message: str | None = None) -> str:
    detail = preview(raw_message)
    base = {
        "missing_binary": "找不到 wx-cli 二进制。",
        "not_initialized": "wx-cli 尚未初始化，需要先人工完成初始化。",
        "wechat_not_running": "微信未运行、未登录或本地数据不可读。",
        "permission_denied": "权限不足，无法执行 wx-cli 或读取必要配置。",
        "parse_error": "wx-cli 输出不可解析或命令返回异常。",
        "timeout": "wx-cli 命令超时。",
        "ok": "wx-cli 连接测试成功。",
    }.get(status, "wx-cli 连接测试失败。")
    return f"{base} {detail}".strip()


def safe_connection_message(status: str, session_count: int = 0) -> str:
    return {
        "ok": f"wx-cli sessions 连接测试成功；仅统计会话数量：{session_count}。",
        "missing_binary": "找不到 wx-cli 二进制；未执行 sessions 连接测试。",
        "not_initialized": "wx-cli 尚未初始化；未读取会话详情。",
        "wechat_not_running": "微信未运行、未登录或本地数据不可读；未读取会话详情。",
        "permission_denied": "权限不足，无法执行 wx-cli；未读取会话详情。",
        "parse_error": "wx-cli sessions 输出不可解析；已隐藏原始输出。",
        "timeout": "wx-cli sessions 命令超时；未读取会话详情。",
    }.get(status, "wx-cli sessions 连接测试失败；已隐藏原始输出。")


def next_action_for_status(status: str) -> str:
    return {
        "missing_binary": "安装 wx-cli，确认 command -v wx 有输出；或在 config/app.yaml 的 wx_cli.binary 填写 wx 绝对路径。",
        "permission_denied": "检查 wx-cli 文件权限，必要时为二进制添加执行权限后重试。",
        "not_initialized": "按 wx-cli 文档人工完成初始化，再回到工作台点击测试连接。",
        "wechat_not_running": "确认微信客户端已运行并登录，再点击测试连接。",
        "parse_error": "检查 wx-cli 版本和 --json 输出格式；不要扩大读取范围。",
        "timeout": "检查 wx-cli 是否卡住或超时，必要时调大 timeout_seconds 后重试。",
        "ok": "wx-cli 二进制可执行；下一步点击测试连接确认初始化和微信登录状态。",
    }.get(status, "查看状态码和本地日志后重试。")


def count_sessions(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("sessions", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 1 if payload else 0
    return 0


def preview(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    text = " ".join(text.strip().split())
    return text[:limit]
