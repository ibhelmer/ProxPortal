#!/usr/bin/env python3
# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Local administrative commands. Run as the same OS user as the portal."""
import argparse
from datetime import timedelta
import getpass
from pathlib import Path
import secrets
import sqlite3
import sys
import time

from app.config import Settings
from app.db import Database
from app.security import hash_password, sha256
from app.services import event, now_iso, local_today
from app.validation import normalize_email, text


def ask_password():
    first = getpass.getpass("Ny adgangskode (14–128 tegn): ")
    second = getpass.getpass("Gentag adgangskoden: ")
    if first != second:
        raise ValueError("Adgangskoderne er ikke ens.")
    return hash_password(first)


def build_parser():
    parser = argparse.ArgumentParser(description="Administrér LabPortalen lokalt på serveren.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Anvend nye databasemigrationer; bevar eksisterende sager.")
    create = sub.add_parser("create-admin", help="Opret en personlig administrator; adgangskoden indtastes skjult.")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    sub.add_parser("list-admins", help="Vis administratorer uden adgangskodehashes.")
    for name in ("reset-password", "disable-admin", "enable-admin"):
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
    backup = sub.add_parser("backup", help="Opret en konsistent SQLite-backup uden aktive websessioner.")
    backup.add_argument("--output", required=True, type=Path)
    sub.add_parser("maintenance", help="Fjern udløbne websessioner og rate-limit-tællere. Ingen sager slettes.")
    expiring = sub.add_parser("list-expiring", help="Vis godkendte/aktive tildelinger som er udløbet eller snart udløber.")
    expiring.add_argument("--days", type=int, default=14)
    reset = sub.add_parser("rotate-status-code", help="Forny en statuskode efter manuel kontrol af ansøgerens identitet.")
    reset.add_argument("--case-number", required=True)
    reset.add_argument("--admin-email", required=True, help="Personlig sagsbehandler, der har kontrolleret identiteten.")
    reset.add_argument("--confirm-identity", action="store_true", help="Bekræft at ansøgerens identitet er kontrolleret.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        db = Database(settings.database_path)
        db.migrate()
        if args.command == "init-db":
            print(f"Databasen er klar: {db.path}")
        elif args.command == "create-admin":
            email, name = normalize_email(args.email), text(args.name, 120)
            if len(name) < 2:
                raise ValueError("Angiv administratorens fulde navn.")
            password_hash = ask_password()
            with db.write() as conn:
                if conn.execute("SELECT 1 FROM admins WHERE email=?", (email,)).fetchone():
                    raise ValueError("Administratoren findes allerede. Brug reset-password eller enable-admin.")
                conn.execute("INSERT INTO admins(email,name,password_hash,created_at) VALUES (?,?,?,?)", (email, name, password_hash, now_iso()))
                conn.execute("INSERT INTO admin_events(action,description,created_at) VALUES (?,?,?)", ("admin_created", f"Lokal serveradministrator oprettede {email}", now_iso()))
            print(f"Administrator oprettet: {email}")
        elif args.command == "list-admins":
            with db.read() as conn:
                for row in conn.execute("SELECT email,name,is_active FROM admins ORDER BY email"):
                    print(f"{row['email']} | {row['name']} | {'aktiv' if row['is_active'] else 'deaktiveret'}")
        elif args.command in {"reset-password", "disable-admin", "enable-admin"}:
            email = normalize_email(args.email)
            password_hash = ask_password() if args.command == "reset-password" else None
            with db.write() as conn:
                row = conn.execute("SELECT * FROM admins WHERE email=?", (email,)).fetchone()
                if not row:
                    raise ValueError("Administratoren findes ikke.")
                if args.command == "reset-password":
                    conn.execute("UPDATE admins SET password_hash=? WHERE id=?", (password_hash, row["id"]))
                elif args.command == "disable-admin":
                    count = conn.execute("SELECT count(*) FROM admins WHERE is_active=1").fetchone()[0]
                    if count <= 1 and row["is_active"]:
                        raise ValueError("Den sidste aktive administrator kan ikke deaktiveres. Opret først en anden konto.")
                    conn.execute("UPDATE admins SET is_active=0 WHERE id=?", (row["id"],))
                else:
                    conn.execute("UPDATE admins SET is_active=1 WHERE id=?", (row["id"],))
                conn.execute("DELETE FROM web_sessions WHERE admin_id=?", (row["id"],))
                conn.execute("INSERT INTO admin_events(actor_id,action,description,created_at) VALUES (?,?,?,?)",
                             (row["id"], args.command, "Udført af lokal serveradministrator; eksisterende websessioner tilbagekaldt", now_iso()))
            print("Administratorkontoen er opdateret. Eksisterende websessioner er tilbagekaldt.")
        elif args.command == "backup":
            db.backup(args.output)
            print(f"Backup oprettet og integritetskontrolleret: {args.output}")
        elif args.command == "maintenance":
            with db.write() as conn:
                sessions = conn.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (int(time.time()),)).rowcount
                limits = conn.execute("DELETE FROM rate_limits WHERE expires_at <= ?", (int(time.time()),)).rowcount
            print(f"Fjernede {sessions} udløbne sessioner og {limits} tællere. Ingen sager eller Proxmox-ressourcer er ændret.")
        elif args.command == "list-expiring":
            if not 0 <= args.days <= 730:
                raise ValueError("--days skal være mellem 0 og 730.")
            end = (local_today(settings) + timedelta(days=args.days)).isoformat()
            with db.read() as conn:
                for row in conn.execute("SELECT case_number,status,ends_on,assigned_node,assigned_vmid,assigned_account FROM cases WHERE archived_at IS NULL AND status IN ('approved','active') AND ends_on<=? ORDER BY ends_on", (end,)):
                    print(" | ".join(str(v) if v is not None else "" for v in row))
        elif args.command == "rotate-status-code":
            if not args.confirm_identity:
                raise ValueError("Kontrollér ansøgerens identitet og tilføj derefter --confirm-identity.")
            code = secrets.token_urlsafe(32)
            with db.write() as conn:
                actor = conn.execute("SELECT id,name FROM admins WHERE email=? AND is_active=1", (normalize_email(args.admin_email),)).fetchone()
                if not actor:
                    raise ValueError("Den angivne sagsbehandler er ikke en aktiv administrator.")
                case = conn.execute("SELECT * FROM cases WHERE case_number=?", (args.case_number.upper(),)).fetchone()
                if not case:
                    raise ValueError("Sagen findes ikke.")
                if case["archived_at"]:
                    raise ValueError("Hent først sagen fra arkivet. Arkiverede sager er skrivebeskyttede.")
                conn.execute("UPDATE cases SET tracking_hash=?,version=version+1,updated_at=? WHERE id=?", (sha256(code), now_iso(), case["id"]))
                conn.execute("UPDATE web_sessions SET status_case_id=NULL WHERE status_case_id=?", (case["id"],))
                event(conn, case["id"], dict(actor), "status_code_reset", case["status"], case["status"],
                      "Den private statuskode er blevet fornyet af administratoren.",
                      "Fornyet fra lokal administrationskommando efter manuel identitetskontrol.")
            print(f"Sagsnummer: {args.case_number.upper()}\nNy privat kode: {code}\nUdlever kun til den verificerede ansøger via en sikker kanal.")
        return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(f"Fejl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
