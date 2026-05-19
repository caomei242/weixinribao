create table if not exists sessions (
  id integer primary key autoincrement,
  external_id text not null unique,
  display_name text not null,
  customer_name text not null default '',
  channel_name text not null default '',
  module_name text not null default '',
  owner_name text not null default '',
  is_whitelisted integer not null default 1,
  enabled integer not null default 1,
  last_success_at text,
  last_cursor text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create index if not exists idx_sessions_whitelist_enabled
on sessions(is_whitelisted, enabled);

create table if not exists people_aliases (
  id integer primary key autoincrement,
  person_name text not null,
  alias text not null,
  role text not null check(role in ('internal', 'customer', 'channel', 'unknown')),
  enabled integer not null default 1,
  unique(alias, role)
);

create table if not exists collection_runs (
  id integer primary key autoincrement,
  mode text not null check(mode in ('fixture', 'real')),
  started_at text not null,
  finished_at text,
  status text not null check(status in ('success', 'partial_failed', 'failed')),
  sessions_total integer not null default 0,
  sessions_success integer not null default 0,
  sessions_failed integer not null default 0,
  raw_messages_seen integer not null default 0,
  raw_messages_inserted integer not null default 0,
  raw_messages_duplicated integer not null default 0,
  candidate_items_created integer not null default 0,
  candidate_items_updated integer not null default 0,
  error_code text,
  error_message text
);

create table if not exists raw_messages (
  id integer primary key autoincrement,
  session_id integer not null references sessions(id),
  message_external_id text,
  local_id text,
  sender_display_name text not null,
  sender_role text not null check(sender_role in ('internal', 'customer', 'channel', 'unknown')),
  sent_at text not null,
  message_type text not null,
  content_text text not null,
  content_hash text not null,
  dedupe_key text not null unique,
  raw_payload_json text not null,
  collection_run_id integer not null references collection_runs(id),
  created_at text not null default current_timestamp
);

create index if not exists idx_raw_messages_session_sent_at
on raw_messages(session_id, sent_at);

create index if not exists idx_raw_messages_content_hash
on raw_messages(content_hash);

create table if not exists candidate_items (
  id integer primary key autoincrement,
  item_code text not null unique,
  item_type text not null check(item_type in ('requirement', 'bug', 'consultation', 'conclusion', 'followup')),
  status text not null check(status in ('pending', 'confirmed', 'rejected')) default 'pending',
  risk_level text not null check(risk_level in ('none', 'low', 'high')) default 'none',
  risk_tags_json text not null default '[]',
  customer_name text not null default '',
  channel_name text not null default '',
  module_name text not null default '',
  title text not null,
  summary text not null,
  suggested_downstream text not null check(suggested_downstream in ('product', 'tech', 'ops', 'manual')),
  aggregate_key text not null unique,
  first_seen_at text not null,
  last_seen_at text not null,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists candidate_item_messages (
  item_id integer not null references candidate_items(id) on delete cascade,
  raw_message_id integer not null references raw_messages(id) on delete cascade,
  evidence_order integer not null default 1,
  primary key(item_id, raw_message_id)
);

create table if not exists manual_reviews (
  id integer primary key autoincrement,
  item_id integer not null references candidate_items(id) on delete cascade,
  review_status text not null check(review_status in ('pending', 'confirmed', 'rejected')),
  owner_name text not null default '',
  priority text not null check(priority in ('P0', 'P1', 'P2', 'P3')) default 'P2',
  downstream text not null check(downstream in ('product', 'tech', 'ops', 'none')) default 'none',
  note text not null default '',
  reviewed_at text not null default current_timestamp,
  reviewed_by text not null default 'local'
);

create table if not exists export_records (
  id integer primary key autoincrement,
  export_date text not null,
  export_type text not null check(export_type in ('feedback_report', 'followup_list', 'daily_review', 'followup_checklist', 'product_tech_summary')),
  file_path text not null,
  filters_json text not null default '{}',
  item_ids_json text not null default '[]',
  template_version text not null,
  generated_at text not null default current_timestamp
);

create index if not exists idx_export_records_date_type
on export_records(export_date, export_type);

create table if not exists quality_feedback (
  id integer primary key autoincrement,
  feedback_date text not null,
  item_id integer references candidate_items(id) on delete set null,
  feedback_type text not null check(feedback_type in ('false_positive', 'missed', 'type_correction', 'risk_correction')),
  note text not null default '',
  from_type text not null default '',
  to_type text not null default '',
  from_risk text not null default '',
  to_risk text not null default '',
  created_at text not null default current_timestamp
);

create index if not exists idx_quality_feedback_date_type
on quality_feedback(feedback_date, feedback_type);

create table if not exists settlement_drafts (
  id integer primary key autoincrement,
  draft_date text not null,
  file_path text not null,
  item_ids_json text not null default '[]',
  summary_json text not null default '{}',
  generated_at text not null default current_timestamp
);

create index if not exists idx_settlement_drafts_date
on settlement_drafts(draft_date, generated_at);
