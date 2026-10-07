# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Local SQLite storage, serialized write transactions and versioned migrations."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Database:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    @contextmanager
    def read(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write(self):
        conn = self.connect()
        try:
            # A single transaction protects case numbers, state changes and audit events.
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.read() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        migrations = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
        supported = {int(p.name.split("_")[0]) for p in migrations}
        with self.read() as conn:
            applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if applied - supported:
            raise RuntimeError("Databasen er nyere end programmet; start den korrekte programversion.")
        for migration in migrations:
            version = int(migration.name.split("_")[0])
            with self.write() as conn:
                if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                    continue
                # executescript would implicitly COMMIT. Execute complete SQL statements instead.
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ""
                if statement.strip() and not all(l.strip().startswith("--") for l in statement.splitlines() if l.strip()):
                    raise RuntimeError(f"Ufuldstændig migration: {migration.name}")
                conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
        try:
            self.path.chmod(0o600)
        except PermissionError:
            pass

    def backup(self, destination: Path):
        destination = Path(destination).resolve()
        if destination == self.path:
            raise ValueError("Backup må ikke overskrive den aktive database.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting an existing backup.
        with destination.open("xb"):
            pass
        destination.chmod(0o600)
        try:
            with self.read() as source:
                target = sqlite3.connect(destination)
                try:
                    source.backup(target)
                    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("Backup bestod ikke integritetskontrollen.")
                    # Backups should not revive web sessions when restored.
                    target.execute("DELETE FROM web_sessions")
                    target.execute("DELETE FROM rate_limits")
                    target.commit()
                finally:
                    target.close()
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
