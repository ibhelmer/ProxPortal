# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Application workflow. No Proxmox API calls or infrastructure mutations occur here."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import csv
import io
import json
import re
import sqlite3

from .db import Database
from .security import sha256, tracking_code, verify_password, DUMMY_HASH, PASSWORD_HASHER
from .validation import text, STATUSES, ROLES, REQUEST_TYPES, OS_FAMILIES


class CaseError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_today(settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def enrich(row, today: date):
    data = dict(row)
    data["duration_days"] = (date.fromisoformat(data["ends_on"]) - date.fromisoformat(data["starts_on"])).days + 1
    data["requested_duration_days"] = (date.fromisoformat(data["requested_ends_on"]) - date.fromisoformat(data["starts_on"])).days + 1
    data["days_left"] = (date.fromisoformat(data["ends_on"]) - today).days
    data["overdue"] = data["status"] in {"approved", "active"} and data["days_left"] < 0 and not data["archived_at"]
    data["soon"] = data["status"] in {"approved", "active"} and 0 <= data["days_left"] <= 14 and not data["archived_at"]
    return data


def event(conn, case_id, actor, action, old_status, new_status, public_note="", internal_note="", details=None):
    conn.execute("""INSERT INTO case_events
        (case_id,actor_id,actor_name,action,old_status,new_status,public_note,internal_note,details_json,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (case_id, actor["id"] if actor else None, actor["name"] if actor else "Ansøger", action,
         old_status, new_status, public_note, internal_note, json.dumps(details or {}, ensure_ascii=False), now_iso()))


def get_admin(db: Database, admin_id):
    if not admin_id:
        return None
    with db.read() as conn:
        row = conn.execute("SELECT id,email,name FROM admins WHERE id=? AND is_active=1", (admin_id,)).fetchone()
        return dict(row) if row else None


def authenticate(db: Database, email: str, password: str):
    with db.read() as conn:
        row = conn.execute("SELECT * FROM admins WHERE email=? COLLATE NOCASE AND is_active=1", (email,)).fetchone()
    valid = verify_password(password, row["password_hash"] if row else DUMMY_HASH)
    if not valid or not row:
        return None
    with db.write() as conn:
        # Recheck state after expensive password verification to avoid a disable/reset race.
        current = conn.execute("SELECT * FROM admins WHERE id=? AND is_active=1 AND password_hash=?", (row["id"], row["password_hash"])).fetchone()
        if not current:
            return None
        if PASSWORD_HASHER.check_needs_rehash(row["password_hash"]):
            conn.execute("UPDATE admins SET password_hash=? WHERE id=?", (PASSWORD_HASHER.hash(password), row["id"]))
        conn.execute("INSERT INTO admin_events(actor_id,action,description,created_at) VALUES (?,?,?,?)",
                     (row["id"], "login", "Administrator loggede ind", now_iso()))
    return {key: row[key] for key in ("id", "email", "name")}


def submit_case(db: Database, settings, data: dict, nonce: str):
    code = tracking_code(settings, nonce)
    with db.write() as conn:
        existing = conn.execute("SELECT * FROM cases WHERE submission_key=?", (nonce,)).fetchone()
        if existing:
            if existing["tracking_hash"] != sha256(code):
                raise CaseError("Sagen er allerede modtaget, men statuskoden er siden blevet fornyet. Brug den senest udleverede kode.", 409)
            return dict(existing), code, False
        year = local_today(settings).year
        conn.execute("""INSERT INTO case_sequences(year,last_value) VALUES (?,1)
                        ON CONFLICT(year) DO UPDATE SET last_value=last_value+1""", (year,))
        sequence = conn.execute("SELECT last_value FROM case_sequences WHERE year=?", (year,)).fetchone()[0]
        number = f"LAB-{year}-{sequence:06d}"
        created = now_iso()
        record = {**data, "case_number": number, "submission_key": nonce,
                  "tracking_hash": sha256(code), "created_at": created, "updated_at": created,
                  "requested_ends_on": data["ends_on"]}
        # Keys are defined by validate_application, never accepted as SQL identifiers from a request.
        allowed = ("case_number", "submission_key", "tracking_hash", "applicant_role", "applicant_name",
                   "class_name", "email", "request_type", "title", "purpose", "os_family", "os_version",
                   "cpu_cores", "ram_gib", "storage_gib", "access_scope", "starts_on", "ends_on",
                   "requested_ends_on", "created_at", "updated_at")
        cursor = conn.execute(f"INSERT INTO cases ({','.join(allowed)}) VALUES ({','.join('?' for _ in allowed)})",
                              [record[key] for key in allowed])
        case_id = cursor.lastrowid
        for student in data.get("participants", []):
            conn.execute("""INSERT INTO case_participants(case_id,student_name,student_email,class_name,created_at)
                            VALUES (?,?,?,?,?)""",
                         (case_id, student["name"], student["email"], student["class_name"], created))
        event(conn, case_id, None, "submitted", None, "pending", "Ansøgningen er modtaget og afventer behandling.")
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return dict(row), code, True


def case_by_id(db: Database, case_id: int, today: date):
    with db.read() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise CaseError("Sagen blev ikke fundet.", 404)
        events = [dict(r) for r in conn.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY id DESC", (case_id,))]
        for item in events:
            item["details"] = json.loads(item["details_json"])
        case = enrich(row, today)
        case["participants"] = [dict(r) for r in conn.execute("""SELECT student_name,student_email,class_name
            FROM case_participants WHERE case_id=? ORDER BY id""", (case_id,))]
        case["lease_requests"] = [dict(r) for r in conn.execute("""SELECT * FROM lease_extension_requests
            WHERE case_id=? ORDER BY id DESC""", (case_id,))]
        case["pending_lease"] = next((r for r in case["lease_requests"] if r["status"] == "pending"), None)
        return case, events


def find_status_case(db: Database, number: str, code: str):
    import hmac
    with db.read() as conn:
        row = conn.execute("SELECT id,tracking_hash FROM cases WHERE case_number=?", (number.upper(),)).fetchone()
    matches = hmac.compare_digest(sha256(code), row["tracking_hash"] if row else "0" * 64)
    return row["id"] if row and matches else None


TRANSITIONS = {
    "review": ({"pending", "rejected"}, "review"),
    "approve": ({"pending", "review"}, "approved"),
    "reject": ({"pending", "review"}, "rejected"),
    "activate": ({"approved"}, "active"),
    "close": ({"pending", "review", "approved", "active"}, "closed"),
}


def change_case(db: Database, settings, case_id: int, actor: dict, form: dict):
    action = form.get("action", "")
    try:
        version = int(form.get("version", ""))
        public_note = text(form.get("public_note", ""), 2000)
        internal_note = text(form.get("internal_note", ""), 4000)
    except ValueError as exc:
        raise CaseError(str(exc)) from None
    with db.write() as conn:
        # Authorization is repeated inside the transaction, not just on the page route.
        if not conn.execute("SELECT 1 FROM admins WHERE id=? AND is_active=1", (actor["id"],)).fetchone():
            raise CaseError("Administratoradgangen er ikke længere aktiv.", 403)
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise CaseError("Sagen blev ikke fundet.", 404)
        if row["version"] != version:
            raise CaseError("Sagen er ændret siden siden blev åbnet. Genindlæs og kontrollér oplysningerne før du fortsætter.", 409)
        if row["archived_at"] and action != "restore":
            raise CaseError("Sagen er arkiveret og skrivebeskyttet. Hent den først fra arkivet.", 409)
        if action in {"extend", "close"} and conn.execute(
                "SELECT 1 FROM lease_extension_requests WHERE case_id=? AND status='pending'", (case_id,)).fetchone():
            raise CaseError("Behandl den afventende forlængelsesanmodning før direkte forlængelse eller afslutning.", 409)
        changes, details = {}, {}
        old_status = row["status"]
        new_status = old_status
        today = local_today(settings)
        if action in TRANSITIONS:
            allowed, new_status = TRANSITIONS[action]
            if old_status not in allowed:
                raise CaseError("Denne handling er ikke tilladt med sagens nuværende status.", 409)
            if action in {"approve", "activate"} and row["ends_on"] < today.isoformat():
                raise CaseError("Den ønskede periode er allerede udløbet. Perioden skal afklares før en ny godkendelse eller levering.")
            if action == "approve":
                if form.get("identity_verified") != "yes":
                    raise CaseError("Kontrollér ansøgerens identitet og tilknytning, og markér bekræftelsen før godkendelse.")
                changes["identity_verified_at"] = now_iso()
                changes["identity_verified_by"] = actor["id"]
                details["Identitet og tilknytning kontrolleret"] = actor["name"]
            if action in {"reject", "close"} and len(public_note) < 3:
                raise CaseError("Skriv en begrundelse i feltet 'Meddelelse til ansøger'.")
            if action == "close" and old_status in {"approved", "active"} and form.get("decommissioned") != "yes":
                raise CaseError("Bekræft først, at VM/adgang er afviklet eller ikke blev oprettet.")
            if action == "activate":
                if row["request_type"] == "vm":
                    try:
                        node = text(form.get("assigned_node", ""), 100)
                        vmid = int(form.get("assigned_vmid", ""))
                        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,99}", node) or not 100 <= vmid <= 999999999:
                            raise ValueError
                    except ValueError:
                        raise CaseError("Angiv et gyldigt nodenavn og et VMID mellem 100 og 999999999.") from None
                    changes.update(assigned_node=node, assigned_vmid=vmid)
                    details.update(Node=node, VMID=vmid)
                else:
                    try:
                        account = text(form.get("assigned_account", ""), 120)
                        if not account:
                            raise ValueError("Angiv den tildelte Proxmox-konto, uden adgangskode.")
                    except ValueError as exc:
                        raise CaseError(str(exc)) from None
                    changes["assigned_account"] = account
                    details["Tildelt konto"] = account
                try:
                    address = text(form.get("assigned_address", ""), 200)
                except ValueError as exc:
                    raise CaseError(str(exc)) from None
                changes["assigned_address"] = address
                details["Adresse / værtsnavn"] = address
            changes["status"] = new_status
        elif action == "archive":
            if old_status not in {"rejected", "closed"}:
                raise CaseError("Kun afviste eller afsluttede sager kan arkiveres. Aktive tildelinger skal afvikles først.", 409)
            if len(internal_note) < 3:
                raise CaseError("Skriv en kort intern arkivbemærkning.")
            changes.update(archived_at=now_iso(), archived_by=actor["id"])
            public_note = ""
        elif action == "restore":
            if not row["archived_at"]:
                raise CaseError("Sagen ligger ikke i arkivet.", 409)
            changes.update(archived_at=None, archived_by=None)
            public_note = ""
        elif action == "note":
            if not public_note and not internal_note:
                raise CaseError("Skriv en meddelelse til ansøgeren eller et internt notat.")
        elif action == "extend":
            if old_status not in {"approved", "active"}:
                raise CaseError("Kun godkendte eller aktive tildelinger kan forlænges.", 409)
            try:
                end = date.fromisoformat(form.get("new_ends_on", ""))
            except (ValueError, TypeError):
                raise CaseError("Angiv en gyldig ny slutdato.") from None
            if end <= date.fromisoformat(row["ends_on"]) or end < today:
                raise CaseError("Den nye slutdato skal ligge efter den nuværende og må ikke ligge i fortiden.")
            if (end - today).days > settings.max_duration_days:
                raise CaseError(f"Forlængelse kan højst ske {settings.max_duration_days} dage frem fra i dag.")
            if len(public_note) < 3:
                raise CaseError("Skriv en begrundelse for forlængelsen til ansøgeren.")
            changes["ends_on"] = end.isoformat()
            details = {"Tidligere slutdato": row["ends_on"], "Ny slutdato": end.isoformat()}
        else:
            raise CaseError("Ukendt handling.")
        if public_note:
            changes["public_message"] = public_note
        changes.update(updated_at=now_iso(), version=version + 1)
        conn.execute(f"UPDATE cases SET {','.join(k+'=?' for k in changes)} WHERE id=? AND version=?",
                     [*changes.values(), case_id, version])
        event(conn, case_id, actor, action, old_status, new_status, public_note, internal_note, details)


def build_filters(query, today: date):
    archive = query.get("archive", "open")
    if archive not in {"open", "archived", "all"}:
        archive = "open"
    filters = {"archive": archive, "q": query.get("q", "").strip()[:160],
               "status": query.get("status", ""), "role": query.get("role", ""),
               "type": query.get("type", ""), "expiry": query.get("expiry", "")}
    clauses, params = [], []
    if archive != "all":
        clauses.append("archived_at IS " + ("NOT NULL" if archive == "archived" else "NULL"))
    for key, choices, column in (("status", STATUSES, "status"), ("role", ROLES, "applicant_role"),
                                  ("type", REQUEST_TYPES, "request_type")):
        if filters[key] in choices:
            clauses.append(f"{column}=?")
            params.append(filters[key])
        else:
            filters[key] = ""
    if filters["q"]:
        escaped = filters["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        columns = ("case_number", "applicant_name", "class_name", "email", "title")
        clauses.append("(" + " OR ".join(c + " LIKE ? ESCAPE '\\'" for c in columns) + ")")
        params.extend([f"%{escaped}%"] * len(columns))
    if filters["expiry"] in {"overdue", "soon"}:
        clauses.append("status IN ('approved','active') AND archived_at IS NULL")
        if filters["expiry"] == "overdue":
            clauses.append("ends_on < ?")
            params.append(today.isoformat())
        else:
            clauses.append("ends_on BETWEEN ? AND ?")
            params.extend([today.isoformat(), (today + timedelta(days=14)).isoformat()])
    else:
        filters["expiry"] = ""
    return " AND ".join(clauses) or "1=1", params, filters


def list_cases(db, settings, query, export=False):
    today = local_today(settings)
    where, params, filters = build_filters(query, today)
    try:
        page = max(1, int(query.get("page", "1")))
    except ValueError:
        page = 1
    with db.read() as conn:
        count = conn.execute(f"SELECT count(*) FROM cases WHERE {where}", params).fetchone()[0]
        pages = max(1, (count + settings.page_size - 1) // settings.page_size)
        page = min(page, pages)
        if export and count > 10000:
            raise CaseError("Eksporten er begrænset til 10.000 sager. Afgræns først med filtre.")
        limit = 10000 if export else settings.page_size
        offset = 0 if export else (page - 1) * settings.page_size
        rows = conn.execute(f"SELECT cases.*, EXISTS (SELECT 1 FROM lease_extension_requests lr WHERE lr.case_id=cases.id AND lr.status='pending') AS has_pending_lease FROM cases WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"cases": [enrich(r, today) for r in rows], "total": count, "page": page, "pages": pages, "filters": filters}


def dashboard_stats(db, settings):
    today = local_today(settings).isoformat()
    with db.read() as conn:
        stats = dict(conn.execute("""SELECT
            sum(CASE WHEN status IN ('pending','review') AND archived_at IS NULL THEN 1 ELSE 0 END) AS waiting,
            sum(CASE WHEN status='approved' AND archived_at IS NULL THEN 1 ELSE 0 END) AS approved,
            sum(CASE WHEN status='active' AND archived_at IS NULL THEN 1 ELSE 0 END) AS active,
            sum(CASE WHEN status IN ('approved','active') AND ends_on<? AND archived_at IS NULL THEN 1 ELSE 0 END) AS overdue,
            sum(CASE WHEN archived_at IS NOT NULL THEN 1 ELSE 0 END) AS archived
            FROM cases""", (today,)).fetchone())
        resources = dict(conn.execute("""SELECT coalesce(sum(cpu_cores),0) AS cpu, coalesce(sum(ram_gib),0) AS ram,
            coalesce(sum(storage_gib),0) AS storage FROM cases
            WHERE status IN ('approved','active') AND archived_at IS NULL AND request_type='vm'""").fetchone())
        pending_extensions = conn.execute("SELECT count(*) FROM lease_extension_requests WHERE status='pending'").fetchone()[0]
    stats = {k: v or 0 for k, v in stats.items()}
    stats["pending_extensions"] = pending_extensions
    return stats, resources


def export_csv(rows):
    def safe(value):
        value = "" if value is None else str(value)
        if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            value = "'" + value
        return value
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow(["Sagsnummer", "Status", "Arkiveret", "Ansøger", "Rolle", "Klasse", "E-mail", "Type", "Titel",
                     "OS", "OS-version", "vCPU", "RAM GiB", "Storage GiB", "Startdato", "Ønsket slutdato",
                     "Gældende slutdato", "Node", "VMID", "Proxmox-konto", "Adresse", "Oprettet"])
    for row in rows:
        values = [row["case_number"], STATUSES[row["status"]], "Ja" if row["archived_at"] else "Nej", row["applicant_name"],
                  ROLES[row["applicant_role"]], row["class_name"], row["email"], REQUEST_TYPES[row["request_type"]], row["title"],
                  OS_FAMILIES.get(row["os_family"], ""), row["os_version"], row["cpu_cores"], row["ram_gib"], row["storage_gib"],
                  row["starts_on"], row["requested_ends_on"], row["ends_on"], row["assigned_node"], row["assigned_vmid"],
                  row["assigned_account"], row["assigned_address"], row["created_at"]]
        writer.writerow([safe(v) for v in values])
    return "\ufeff" + stream.getvalue()


def request_lease_extension(db: Database, settings, case_id: int, form: dict):
    """Applicant with an authorized status session may request, never approve, a lease extension."""
    try:
        proposed = date.fromisoformat(form.get("new_ends_on", ""))
        if proposed.isoformat() != form.get("new_ends_on", ""):
            raise ValueError
    except (TypeError, ValueError):
        raise CaseError("Angiv en gyldig ny slutdato.") from None
    try:
        reason = text(form.get("reason", ""), 1600)
    except ValueError as exc:
        raise CaseError(str(exc)) from None
    if len(reason) < 10:
        raise CaseError("Begrundelsen skal være mindst 10 tegn.")
    with db.write() as conn:
        case = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise CaseError("Sagen findes ikke.", 404)
        if case["archived_at"] or case["status"] not in {"approved", "active"}:
            raise CaseError("Der kan kun søges om forlængelse af godkendte eller aktive tildelinger.", 409)
        today = local_today(settings)
        if proposed <= date.fromisoformat(case["ends_on"]) or proposed <= today:
            raise CaseError("Ny slutdato skal ligge efter gældende slutdato og i fremtiden.")
        if (proposed - today).days > settings.max_duration_days:
            raise CaseError(f"Ny slutdato må højst ligge {settings.max_duration_days} dage fremme.")
        if conn.execute("SELECT 1 FROM lease_extension_requests WHERE case_id=? AND status='pending'", (case_id,)).fetchone():
            raise CaseError("Der afventer allerede en forlængelsesanmodning.", 409)
        conn.execute("""INSERT INTO lease_extension_requests(case_id,proposed_ends_on,reason,created_at)
                        VALUES (?,?,?,?)""", (case_id, proposed.isoformat(), reason, now_iso()))
        conn.execute("UPDATE cases SET version=version+1,updated_at=? WHERE id=?", (now_iso(), case_id))
        event(conn, case_id, None, "lease_requested", case["status"], case["status"],
              "Der er ansøgt om forlængelse til " + proposed.isoformat() + ".", details={"Ønsket slutdato": proposed.isoformat()})


def decide_lease_extension(db: Database, settings, case_id: int, actor: dict, form: dict):
    """Admin-only decision; updates lease end only when approved, all within one write tx."""
    try:
        version = int(form.get("version", ""))
        lease_id = int(form.get("lease_id", ""))
        decision = form.get("decision", "")
        note = text(form.get("decision_note", ""), 1600)
    except (ValueError, TypeError) as exc:
        raise CaseError("Ugyldig beslutning eller meddelelse.") from exc
    if decision not in {"approve", "reject"} or len(note) < 3:
        raise CaseError("Vælg beslutning og skriv mindst tre tegn som begrundelse.")
    with db.write() as conn:
        if not conn.execute("SELECT 1 FROM admins WHERE id=? AND is_active=1", (actor["id"],)).fetchone():
            raise CaseError("Administratoradgangen er ikke aktiv.", 403)
        case = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case:
            raise CaseError("Sagen findes ikke.", 404)
        if case["version"] != version:
            raise CaseError("Sagen er ændret. Genindlæs og kontrollér før afgørelse.", 409)
        if case["archived_at"] or case["status"] not in {"approved", "active"}:
            raise CaseError("Sagens status tillader ikke denne afgørelse.", 409)
        lease = conn.execute("""SELECT * FROM lease_extension_requests
            WHERE id=? AND case_id=? AND status='pending'""", (lease_id, case_id)).fetchone()
        if not lease:
            raise CaseError("Forlængelsesanmodningen er allerede behandlet eller findes ikke.", 409)
        if decision == "approve":
            proposed = date.fromisoformat(lease["proposed_ends_on"])
            today = local_today(settings)
            if proposed <= date.fromisoformat(case["ends_on"]) or proposed <= today or (proposed - today).days > settings.max_duration_days:
                raise CaseError("Den anmodede periode kan ikke længere godkendes. Afvis anmodningen og bed om en ny.", 409)
            conn.execute("UPDATE cases SET ends_on=?,version=version+1,updated_at=?,public_message=? WHERE id=?",
                         (proposed.isoformat(), now_iso(), note, case_id))
        else:
            conn.execute("UPDATE cases SET version=version+1,updated_at=?,public_message=? WHERE id=?",
                         (now_iso(), note, case_id))
        target_status = "approved" if decision == "approve" else "rejected"
        conn.execute("""UPDATE lease_extension_requests SET status=?,decided_by=?,decided_at=?,decision_note=?
                        WHERE id=? AND status='pending'""", (target_status, actor["id"], now_iso(), note, lease_id))
        event(conn, case_id, actor, "lease_approved" if decision == "approve" else "lease_rejected",
              case["status"], case["status"], note, details={"Ønsket slutdato": lease["proposed_ends_on"]})
