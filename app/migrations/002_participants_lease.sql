-- Copyright 2026 Ib Helmer Nielsen
-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE case_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    student_name TEXT NOT NULL,
    student_email TEXT NOT NULL,
    class_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(case_id, student_email COLLATE NOCASE)
);
CREATE INDEX case_participants_case ON case_participants(case_id);
CREATE TABLE lease_extension_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id),
    proposed_ends_on TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by INTEGER REFERENCES admins(id),
    decision_note TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX lease_extension_one_pending ON lease_extension_requests(case_id) WHERE status='pending';
CREATE INDEX lease_extension_case ON lease_extension_requests(case_id, id);
