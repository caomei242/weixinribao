from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import AppConfig


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    migrate_export_records(conn)
    conn.commit()


def migrate_export_records(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "select sql from sqlite_master where type = 'table' and name = 'export_records'"
    ).fetchone()
    if row is None or "product_tech_summary" in str(row["sql"]):
        return

    conn.execute("drop table if exists export_records_legacy")
    conn.execute("alter table export_records rename to export_records_legacy")
    conn.execute(
        """
        create table export_records (
          id integer primary key autoincrement,
          export_date text not null,
          export_type text not null check(export_type in (
            'feedback_report',
            'followup_list',
            'daily_review',
            'followup_checklist',
            'product_tech_summary'
          )),
          file_path text not null,
          filters_json text not null default '{}',
          item_ids_json text not null default '[]',
          template_version text not null,
          generated_at text not null default current_timestamp
        )
        """
    )
    conn.execute(
        """
        insert into export_records (
          id, export_date, export_type, file_path, filters_json, item_ids_json,
          template_version, generated_at
        )
        select id, export_date, export_type, file_path, filters_json, item_ids_json,
               template_version, generated_at
        from export_records_legacy
        """
    )
    conn.execute("drop table export_records_legacy")
    conn.execute(
        """
        create index if not exists idx_export_records_date_type
        on export_records(export_date, export_type)
        """
    )


def seed_config(conn: sqlite3.Connection, config: AppConfig) -> None:
    for session in config.sessions:
        conn.execute(
            """
            insert into sessions (
              external_id, display_name, customer_name, channel_name, module_name,
              owner_name, is_whitelisted, enabled, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            on conflict(external_id) do update set
              display_name = excluded.display_name,
              customer_name = excluded.customer_name,
              channel_name = excluded.channel_name,
              module_name = excluded.module_name,
              owner_name = excluded.owner_name,
              is_whitelisted = excluded.is_whitelisted,
              enabled = excluded.enabled,
              updated_at = current_timestamp
            """,
            (
                session.external_id,
                session.display_name,
                session.customer_name,
                session.channel_name,
                session.module_name,
                session.owner_name,
                1 if session.is_whitelisted else 0,
                1 if session.enabled else 0,
            ),
        )

    for person in config.internal_people:
        aliases = {person.person_name, person.wechat_display_name, *person.aliases}
        for alias in aliases:
            if not alias:
                continue
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


def setup_database(config: AppConfig) -> sqlite3.Connection:
    conn = connect(Path(config.root) / config.database.path)
    init_db(conn)
    seed_config(conn, config)
    return conn
