from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TRIAL_SESSION_NAME = "襄城县大斌网络科技有限公司X稿定"
SECOND_TEST_GROUP_ID = "local-monitor-qiajie-gaoding"
SECOND_TEST_GROUP_NAME = "洽姐x稿定电商"


@dataclass
class AppSettings:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class DatabaseConfig:
    path: str = "data/wechat_feedback.sqlite3"


@dataclass
class WxCliConfig:
    mode: str = "fixture"
    binary: str = "wx"
    timeout_seconds: int = 15
    fixture_dir: str = "fixtures"
    real_read_enabled: bool = False
    real_allowed_session: str = TRIAL_SESSION_NAME
    real_lookback_hours: int = 2
    real_limit: int = 50
    real_start_at: str = ""
    real_end_at: str = ""
    expanded_real_lookback_days: float = 30
    expanded_real_max_groups: int = 20
    expanded_real_max_total_messages: int = 5000
    expanded_real_max_messages_per_group: int = 500
    expanded_real_batch_limit: int = 1
    persistent_real_read_enabled: bool = False
    persistent_real_read_paused: bool = False
    persistent_real_read_test_account_confirmed: bool = False
    persistent_real_read_schedule_enabled: bool = False
    persistent_real_read_interval_minutes: int = 60
    persistent_real_read_default_lookback_days: float = 30


@dataclass
class CollectorConfig:
    interval_minutes: int = 60
    lookback_minutes: int = 120


@dataclass
class ExportConfig:
    directory: str = "exports"


@dataclass
class SessionConfig:
    external_id: str
    display_name: str
    customer_name: str = ""
    channel_name: str = ""
    module_name: str = ""
    owner_name: str = ""
    customer_stage: str = ""
    group_type: str = ""
    common_contacts: list[str] = field(default_factory=list)
    reply_notes: str = ""
    is_whitelisted: bool = True
    enabled: bool = True
    verification_status: str = "verified"
    daily_monitor_enabled: bool = True
    include_in_daily: bool = True
    trial_scope: str = "最近50条"
    internal_people: list[str] = field(default_factory=list)
    owner_names: list[str] = field(default_factory=list)
    roster_member_names: list[str] = field(default_factory=list)
    archived: bool = False
    display_name_status: str = "resolved"
    display_name_source: str = ""
    display_name_reason_code: str = ""
    history_target: str = ""
    wx_session_token: str = ""
    source_session_id: str = ""


@dataclass
class PersonConfig:
    person_name: str
    aliases: list[str] = field(default_factory=list)
    wechat_display_name: str = ""
    role: str = "我方人员"
    modules: list[str] = field(default_factory=list)
    enabled: bool = True
    notes: str = ""


@dataclass
class RiskConfig:
    keywords: list[str] = field(default_factory=list)
    sensitive_keywords: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    app: AppSettings = field(default_factory=AppSettings)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    wx_cli: WxCliConfig = field(default_factory=WxCliConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    sessions: list[SessionConfig] = field(default_factory=list)
    internal_people: list[PersonConfig] = field(default_factory=list)
    risk: RiskConfig = field(default_factory=RiskConfig)
    root: Path = field(default_factory=Path.cwd)


def default_config(root: Path | None = None) -> AppConfig:
    base = root or Path.cwd()
    return AppConfig(
        sessions=[
            SessionConfig(
                "customer-a",
                "客户A项目群",
                "客户A",
                "",
                "订单",
                "张三",
                "试用期",
                "客户项目群",
                ["客户A对接人"],
                "先确认订单信息再对外回复",
            ),
            SessionConfig(
                "customer-b",
                "客户B售后群",
                "客户B",
                "",
                "登录",
                "李四",
                "交付期",
                "售后群",
                ["客户B对接人"],
                "问题类先归因再回复",
            ),
            SessionConfig(
                "channel-c",
                "渠道C协作群",
                "",
                "渠道C",
                "渠道",
                "王五",
                "合作期",
                "渠道协作群",
                ["渠道C对接人"],
                "涉及商务口径先内部确认",
            ),
            second_test_group_config(),
        ],
        internal_people=[
            PersonConfig("张三", ["张三", "Jason"]),
            PersonConfig("李四", ["李四", "Lisi"]),
        ],
        risk=RiskConfig(
            keywords=["报价", "合同", "金额", "投诉", "赔偿", "退款", "回复"],
            sensitive_keywords=["身份证", "手机号", "隐私"],
        ),
        root=base,
    )


def load_config(path: Path | str | None = None, root: Path | None = None) -> AppConfig:
    base = root or Path.cwd()
    config = default_config(base)
    if path is None:
        return config

    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = base / config_path
    if not config_path.exists():
        return config

    data = _load_yaml_like(config_path)
    if not data:
        return config

    app = data.get("app", {})
    config.app.host = str(app.get("host", config.app.host))
    config.app.port = int(app.get("port", config.app.port))

    database = data.get("database", {})
    config.database.path = str(database.get("path", config.database.path))

    wx_cli = data.get("wx_cli", {})
    config.wx_cli.mode = str(wx_cli.get("mode", config.wx_cli.mode))
    config.wx_cli.binary = str(wx_cli.get("binary", config.wx_cli.binary))
    config.wx_cli.timeout_seconds = int(
        wx_cli.get("timeout_seconds", config.wx_cli.timeout_seconds)
    )
    config.wx_cli.fixture_dir = str(wx_cli.get("fixture_dir", config.wx_cli.fixture_dir))
    config.wx_cli.real_read_enabled = _parse_bool(
        wx_cli.get("real_read_enabled", config.wx_cli.real_read_enabled)
    )
    config.wx_cli.real_allowed_session = str(
        wx_cli.get("real_allowed_session", config.wx_cli.real_allowed_session)
    )
    config.wx_cli.real_lookback_hours = int(
        wx_cli.get("real_lookback_hours", config.wx_cli.real_lookback_hours)
    )
    config.wx_cli.real_limit = int(wx_cli.get("real_limit", config.wx_cli.real_limit))
    config.wx_cli.real_start_at = str(
        wx_cli.get("real_start_at", config.wx_cli.real_start_at)
    )
    config.wx_cli.real_end_at = str(
        wx_cli.get("real_end_at", config.wx_cli.real_end_at)
    )
    config.wx_cli.expanded_real_lookback_days = float(
        wx_cli.get(
            "expanded_real_lookback_days",
            config.wx_cli.expanded_real_lookback_days,
        )
    )
    config.wx_cli.expanded_real_max_groups = int(
        wx_cli.get("expanded_real_max_groups", config.wx_cli.expanded_real_max_groups)
    )
    config.wx_cli.expanded_real_max_total_messages = int(
        wx_cli.get(
            "expanded_real_max_total_messages",
            config.wx_cli.expanded_real_max_total_messages,
        )
    )
    config.wx_cli.expanded_real_max_messages_per_group = int(
        wx_cli.get(
            "expanded_real_max_messages_per_group",
            config.wx_cli.expanded_real_max_messages_per_group,
        )
    )
    config.wx_cli.expanded_real_batch_limit = int(
        wx_cli.get(
            "expanded_real_batch_limit",
            config.wx_cli.expanded_real_batch_limit,
        )
    )
    config.wx_cli.persistent_real_read_enabled = _parse_bool(
        wx_cli.get(
            "persistent_real_read_enabled",
            config.wx_cli.persistent_real_read_enabled,
        )
    )
    config.wx_cli.persistent_real_read_paused = _parse_bool(
        wx_cli.get(
            "persistent_real_read_paused",
            config.wx_cli.persistent_real_read_paused,
        )
    )
    config.wx_cli.persistent_real_read_test_account_confirmed = _parse_bool(
        wx_cli.get(
            "persistent_real_read_test_account_confirmed",
            config.wx_cli.persistent_real_read_test_account_confirmed,
        )
    )
    config.wx_cli.persistent_real_read_schedule_enabled = _parse_bool(
        wx_cli.get(
            "persistent_real_read_schedule_enabled",
            config.wx_cli.persistent_real_read_schedule_enabled,
        )
    )
    config.wx_cli.persistent_real_read_interval_minutes = int(
        wx_cli.get(
            "persistent_real_read_interval_minutes",
            config.wx_cli.persistent_real_read_interval_minutes,
        )
    )
    config.wx_cli.persistent_real_read_default_lookback_days = float(
        wx_cli.get(
            "persistent_real_read_default_lookback_days",
            config.wx_cli.persistent_real_read_default_lookback_days,
        )
    )

    collector = data.get("collector", {})
    config.collector.interval_minutes = int(
        collector.get("interval_minutes", config.collector.interval_minutes)
    )
    config.collector.lookback_minutes = int(
        collector.get("lookback_minutes", config.collector.lookback_minutes)
    )

    export = data.get("export", {})
    config.export.directory = str(export.get("directory", config.export.directory))

    if "sessions" in data:
        config.sessions = [
            SessionConfig(
                external_id=str(item.get("external_id", "")),
                display_name=str(item.get("display_name", "")),
                customer_name=str(item.get("customer_name", "")),
                channel_name=str(item.get("channel_name", "")),
                module_name=str(item.get("module_name", "")),
                owner_name=str(item.get("owner_name", "")),
                customer_stage=str(item.get("customer_stage", "")),
                group_type=str(item.get("group_type", "")),
                common_contacts=_parse_text_list(item.get("common_contacts", [])),
                reply_notes=str(item.get("reply_notes", "")),
                is_whitelisted=_parse_bool(item.get("is_whitelisted", True)),
                enabled=_parse_bool(item.get("enabled", True)),
                verification_status=str(
                    item.get("verification_status", "verified")
                ),
                daily_monitor_enabled=_parse_bool(
                    item.get("daily_monitor_enabled", True)
                ),
                include_in_daily=_parse_bool(item.get("include_in_daily", True)),
                trial_scope=str(item.get("trial_scope", "最近50条")),
                internal_people=_parse_text_list(item.get("internal_people", [])),
                owner_names=_parse_text_list(
                    item.get("owner_names", item.get("owner_name", ""))
                ),
                roster_member_names=_parse_text_list(
                    item.get("roster_member_names", [])
                ),
                archived=_parse_bool(item.get("archived", False)),
                display_name_status=str(
                    item.get("display_name_status", "resolved")
                ),
                display_name_source=str(item.get("display_name_source", "")),
                display_name_reason_code=str(
                    item.get("display_name_reason_code", "")
                ),
                history_target=str(item.get("history_target", "")),
                wx_session_token=str(item.get("wx_session_token", "")),
                source_session_id=str(item.get("source_session_id", "")),
            )
            for item in data.get("sessions", [])
            if item.get("external_id")
        ]
        for session in config.sessions:
            if session.owner_names:
                session.owner_name = session.owner_names[0]
            elif session.owner_name:
                session.owner_names = _parse_text_list(session.owner_name)

    if "internal_people" in data:
        config.internal_people = [
            PersonConfig(
                person_name=str(item.get("person_name", "")),
                aliases=_parse_text_list(item.get("aliases", [])),
                wechat_display_name=str(item.get("wechat_display_name", "")),
                role=str(item.get("role", "我方人员")),
                modules=_parse_text_list(item.get("modules", [])),
                enabled=_parse_bool(item.get("enabled", True)),
                notes=str(item.get("notes", "")),
            )
            for item in data.get("internal_people", [])
            if item.get("person_name")
        ]

    risk = data.get("risk", {})
    if "keywords" in risk:
        config.risk.keywords = [str(item) for item in risk.get("keywords", [])]
    if "sensitive_keywords" in risk:
        config.risk.sensitive_keywords = [
            str(item) for item in risk.get("sensitive_keywords", [])
        ]

    ensure_default_monitor_groups(config)
    return config


def second_test_group_config() -> SessionConfig:
    return SessionConfig(
        SECOND_TEST_GROUP_ID,
        SECOND_TEST_GROUP_NAME,
        "",
        "",
        "电商设计",
        "",
        "试读验证",
        "测试群",
        [],
        "",
        True,
        True,
        "pending_verification",
        True,
        False,
        "最近50条",
        [],
    )


def ensure_default_monitor_groups(config: AppConfig) -> None:
    existing_ids = {session.external_id for session in config.sessions}
    existing_names = {session.display_name for session in config.sessions}
    if SECOND_TEST_GROUP_ID in existing_ids or SECOND_TEST_GROUP_NAME in existing_names:
        return
    config.sessions.append(second_test_group_config())


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def session_by_external_id(config: AppConfig) -> dict[str, SessionConfig]:
    return {session.external_id: session for session in config.sessions}


def internal_aliases(config: AppConfig) -> set[str]:
    aliases: set[str] = set()
    for person in config.internal_people:
        if not person.enabled:
            continue
        aliases.add(person.person_name)
        if person.wechat_display_name:
            aliases.add(person.wechat_display_name)
        aliases.update(person.aliases)
    return aliases


def _load_yaml_like(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded or {}
    except Exception:
        return _parse_small_yaml(path.read_text(encoding="utf-8"))


def _parse_small_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current_section: str | None = None
    current_list_item: dict[str, Any] | None = None
    nested_section: str | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":"):
            current_section = line[:-1]
            nested_section = None
            current_list_item = None
            root[current_section] = [] if current_section in {"sessions", "internal_people"} else {}
            continue

        if current_section is None:
            continue

        section = root[current_section]
        if isinstance(section, list):
            if line.startswith("- "):
                current_list_item = {}
                section.append(current_list_item)
                key, value = line[2:].split(":", 1)
                current_list_item[key.strip()] = _parse_scalar(value.strip())
                nested_section = None
            elif current_list_item is not None and ":" in line:
                key, value = line.split(":", 1)
                current_list_item[key.strip()] = _parse_scalar(value.strip())
            continue

        if indent == 2 and ":" in line:
            key, value = line.split(":", 1)
            if value.strip():
                section[key.strip()] = _parse_scalar(value.strip())
                nested_section = None
            else:
                nested_section = key.strip()
                section[nested_section] = []
        elif indent >= 4 and nested_section and line.startswith("- "):
            section[nested_section].append(_parse_scalar(line[2:].strip()))

    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _parse_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.replace("，", ",").replace("\r", "\n").replace(",", "\n").split("\n")
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]
