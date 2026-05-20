from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import AppConfig, internal_aliases, session_by_external_id
from .db import seed_config
from .extractor import content_hash, dedupe_key_for_message, extract_candidate
from .wx_cli_adapter import NormalizedMessage, WxCliUnavailable, fetch_messages


@dataclass
class CollectionResult:
    run_id: int
    mode: str
    status: str
    sessions_total: int
    sessions_success: int
    sessions_failed: int
    raw_messages_seen: int
    raw_messages_inserted: int
    raw_messages_duplicated: int
    candidate_items_created: int
    candidate_items_updated: int
    error_code: str | None = None
    error_message: str | None = None


def collect_fixture_messages(config: AppConfig, conn: sqlite3.Connection) -> CollectionResult:
    return collect_messages(config, conn)


def collect_messages(config: AppConfig, conn: sqlite3.Connection) -> CollectionResult:
    seed_config(conn, config)
    started_at = now_iso()
    run_id = _start_run(conn, config.wx_cli.mode, started_at)

    try:
        fetched = fetch_messages(config)
    except WxCliUnavailable as exc:
        _finish_run(
            conn,
            run_id,
            status="failed",
            error_code=exc.code,
            error_message=exc.message,
        )
        return CollectionResult(
            run_id=run_id,
            mode=config.wx_cli.mode,
            status="failed",
            sessions_total=len(config.sessions),
            sessions_success=0,
            sessions_failed=len(config.sessions),
            raw_messages_seen=0,
            raw_messages_inserted=0,
            raw_messages_duplicated=0,
            candidate_items_created=0,
            candidate_items_updated=0,
            error_code=exc.code,
            error_message=exc.message,
        )

    return collect_normalized_messages(
        config,
        conn,
        fetched,
        mode=config.wx_cli.mode,
        run_id=run_id,
    )


def collect_normalized_messages(
    config: AppConfig,
    conn: sqlite3.Connection,
    messages: list[NormalizedMessage | dict],
    *,
    mode: str | None = None,
    run_id: int | None = None,
) -> CollectionResult:
    seed_config(conn, config)
    if run_id is None:
        run_id = _start_run(conn, mode or config.wx_cli.mode, now_iso())
    fetched = [
        message.as_dict() if isinstance(message, NormalizedMessage) else dict(message)
        for message in messages
    ]
    sessions = session_by_external_id(config)
    aliases = internal_aliases(config)
    inserted = 0
    duplicated = 0
    candidate_created = 0
    candidate_updated = 0

    for message in fetched:
        session = sessions.get(message["session_external_id"])
        if session is None or not session.is_whitelisted or not session.enabled:
            continue

        sender_role = infer_sender_role(message, session, aliases)
        message["sender_role"] = sender_role
        dedupe_key = dedupe_key_for_message(message)
        digest = content_hash(message["content_text"])
        session_row = conn.execute(
            "select id from sessions where external_id = ?", (session.external_id,)
        ).fetchone()

        try:
            cursor = conn.execute(
                """
                insert into raw_messages (
                  session_id, message_external_id, local_id, sender_display_name,
                  sender_role, sent_at, message_type, content_text, content_hash,
                  dedupe_key, raw_payload_json, collection_run_id
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_row["id"],
                    message.get("message_external_id"),
                    message.get("local_id"),
                    message.get("sender_display_name", ""),
                    sender_role,
                    message["sent_at"],
                    message.get("message_type", "text"),
                    message.get("content_text", ""),
                    digest,
                    dedupe_key,
                    json.dumps(message.get("raw_payload", message), ensure_ascii=False),
                    run_id,
                ),
            )
            raw_message_id = int(cursor.lastrowid)
            inserted += 1
        except sqlite3.IntegrityError:
            duplicated += 1
            continue

        draft = extract_candidate(message, session, config)
        if draft is None:
            continue

        item_id, created = upsert_candidate(conn, draft)
        if created:
            candidate_created += 1
        else:
            candidate_updated += 1
        conn.execute(
            """
            insert or ignore into candidate_item_messages
              (item_id, raw_message_id, evidence_order)
            values (
              ?,
              ?,
              (select coalesce(max(evidence_order), 0) + 1
               from candidate_item_messages where item_id = ?)
            )
            """,
            (item_id, raw_message_id, item_id),
        )

    sessions_seen = {
        message["session_external_id"]
        for message in fetched
        if message["session_external_id"] in sessions
    }
    _finish_run(
        conn,
        run_id,
        status="success",
        sessions_total=len([s for s in config.sessions if s.enabled and s.is_whitelisted]),
        sessions_success=len(sessions_seen),
        sessions_failed=0,
        raw_messages_seen=len(fetched),
        raw_messages_inserted=inserted,
        raw_messages_duplicated=duplicated,
        candidate_items_created=candidate_created,
        candidate_items_updated=candidate_updated,
    )
    conn.commit()
    return CollectionResult(
        run_id=run_id,
        mode=mode or config.wx_cli.mode,
        status="success",
        sessions_total=len([s for s in config.sessions if s.enabled and s.is_whitelisted]),
        sessions_success=len(sessions_seen),
        sessions_failed=0,
        raw_messages_seen=len(fetched),
        raw_messages_inserted=inserted,
        raw_messages_duplicated=duplicated,
        candidate_items_created=candidate_created,
        candidate_items_updated=candidate_updated,
    )

def infer_sender_role(message: dict[str, str], session, aliases: set[str]) -> str:
    hinted = message.get("raw_payload", {}).get("sender_role") or message.get("sender_role")
    if hinted in {"internal", "customer", "channel", "unknown"}:
        return hinted
    if message.get("sender_display_name") in aliases:
        return "internal"
    if session.channel_name:
        return "channel"
    if session.customer_name:
        return "customer"
    return "unknown"


def upsert_candidate(conn: sqlite3.Connection, draft) -> tuple[int, bool]:
    existing = conn.execute(
        "select id from candidate_items where aggregate_key = ?", (draft.aggregate_key,)
    ).fetchone()
    if existing:
        conn.execute(
            """
            update candidate_items
            set last_seen_at = ?, updated_at = current_timestamp
            where id = ?
            """,
            (draft.last_seen_at, existing["id"]),
        )
        return int(existing["id"]), False

    item_code = next_item_code(conn, draft.item_type)
    cursor = conn.execute(
        """
        insert into candidate_items (
          item_code, item_type, status, risk_level, risk_tags_json,
          customer_name, channel_name, module_name, title, summary,
          suggested_downstream, aggregate_key, first_seen_at, last_seen_at
        )
        values (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_code,
            draft.item_type,
            draft.risk_level,
            json.dumps(draft.risk_tags, ensure_ascii=False),
            draft.customer_name,
            draft.channel_name,
            draft.module_name,
            draft.title,
            draft.summary,
            draft.suggested_downstream,
            draft.aggregate_key,
            draft.first_seen_at,
            draft.last_seen_at,
        ),
    )
    return int(cursor.lastrowid), True


def next_item_code(conn: sqlite3.Connection, item_type: str) -> str:
    prefix = {
        "requirement": "R",
        "bug": "B",
        "consultation": "Q",
        "conclusion": "C",
        "followup": "F",
    }[item_type]
    count = conn.execute(
        "select count(*) from candidate_items where item_code like ?",
        (f"{prefix}-%",),
    ).fetchone()[0]
    return f"{prefix}-{count + 1:03d}"


def latest_run(conn: sqlite3.Connection) -> dict[str, object]:
    row = conn.execute(
        "select * from collection_runs order by id desc limit 1"
    ).fetchone()
    return dict(row) if row else {}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _start_run(conn: sqlite3.Connection, mode: str, started_at: str) -> int:
    cursor = conn.execute(
        """
        insert into collection_runs (mode, started_at, status)
        values (?, ?, 'failed')
        """,
        (mode, started_at),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _finish_run(conn: sqlite3.Connection, run_id: int, **fields) -> None:
    fields.setdefault("finished_at", now_iso())
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values())
    values.append(run_id)
    conn.execute(f"update collection_runs set {assignments} where id = ?", values)
    conn.commit()
