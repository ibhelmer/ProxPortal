-- Copyright 2026 Ib Helmer Nielsen
-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at TEXT NOT NULL
);
CREATE TABLE cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT NOT NULL UNIQUE,
    submission_key TEXT NOT NULL UNIQUE,
    tracking_hash TEXT NOT NULL,
    applicant_role TEXT NOT NULL CHECK(applicant_role IN ('student','teacher')),
    applicant_name TEXT NOT NULL,
    class_name TEXT,
    email TEXT NOT NULL,
    request_type TEXT NOT NULL CHECK(request_type IN ('vm','access')),
    title TEXT NOT NULL,
    purpose TEXT NOT NULL,
    os_family TEXT,
    os_version TEXT,
    cpu_cores INTEGER,
    ram_gib INTEGER,
    storage_gib INTEGER,
    access_scope TEXT,
    starts_on TEXT NOT NULL,
    requested_ends_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','review','approved','active','rejected','closed')),
    public_message TEXT NOT NULL DEFAULT '',
    identity_verified_at TEXT,
    identity_verified_by INTEGER REFERENCES admins(id),
    assigned_node TEXT NOT NULL DEFAULT '',
    assigned_vmid INTEGER,
    assigned_account TEXT NOT NULL DEFAULT '',
    assigned_address TEXT NOT NULL DEFAULT '',
    archived_at TEXT,
    archived_by INTEGER REFERENCES admins(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CHECK(applicant_role <> 'student' OR (class_name IS NOT NULL AND length(trim(class_name)) > 0)),
    CHECK(starts_on <= requested_ends_on),
    CHECK(starts_on <= ends_on),
    CHECK(archived_at IS NULL OR status IN ('rejected','closed')),
    CHECK(
        (request_type='vm' AND os_family IS NOT NULL AND os_version IS NOT NULL
            AND cpu_cores IS NOT NULL AND ram_gib IS NOT NULL AND storage_gib IS NOT NULL
            AND cpu_cores > 0 AND ram_gib > 0 AND storage_gib > 0
            AND access_scope IS NULL)
        OR
        (request_type='access' AND access_scope IS NOT NULL AND length(trim(access_scope)) > 0
            AND os_family IS NULL AND os_version IS NULL AND cpu_cores IS NULL
            AND ram_gib IS NULL AND storage_gib IS NULL)
    )
);
CREATE INDEX cases_status ON cases(status, archived_at);
CREATE INDEX cases_expiry ON cases(ends_on);
CREATE INDEX cases_email ON cases(email);
CREATE TABLE case_sequences (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL CHECK(last_value >= 1)
);
CREATE TABLE case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    actor_id INTEGER REFERENCES admins(id),
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    public_note TEXT NOT NULL DEFAULT '',
    internal_note TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX case_events_case ON case_events(case_id, id);
-- Application-level history is append-only, including accidental SQL writes.
-- This is not a tamper-proof audit store against a database/server administrator.
CREATE TRIGGER case_events_no_update BEFORE UPDATE ON case_events
BEGIN SELECT RAISE(ABORT, 'Case history is append-only'); END;
CREATE TRIGGER case_events_no_delete BEFORE DELETE ON case_events
BEGIN SELECT RAISE(ABORT, 'Case history is append-only'); END;
CREATE TABLE web_sessions (
    token_hash TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    admin_id INTEGER REFERENCES admins(id),
    status_case_id INTEGER REFERENCES cases(id),
    expires_at INTEGER NOT NULL
);
CREATE INDEX web_sessions_expiry ON web_sessions(expires_at);
CREATE TABLE rate_limits (
    bucket_key TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    hits INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    PRIMARY KEY(bucket_key, window_start)
);
CREATE INDEX rate_limits_expiry ON rate_limits(expires_at);
CREATE TABLE admin_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES admins(id),
    action TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
