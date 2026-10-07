# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import csv
import io
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.db import Database
from app.main import create_app
from app.security import COOKIE_NAME, sha256, hash_password, verify_password, rate_limit
from app import services
from app.validation import validate_application
from conftest import hidden, form_data, submit, login, action, valid_data, ADMIN_PASSWORD

@pytest.mark.parametrize("path", ["/", "/apply", "/status", "/admin/login", "/privacy", "/about", "/healthz", "/static/style.css", "/static/app.js"])
def test_public_pages(client, path):
    assert client.get(path).status_code == 200


def test_submission_student_vm_and_private_status(client, settings, db):
    case, code = submit(client, settings)
    assert case["case_number"].startswith(f"LAB-{services.local_today(settings).year}-")
    assert case["class_name"] == "itt-csd-s26"
    assert case["cpu_cores"] == 2 and case["ram_gib"] == 4 and case["storage_gib"] == 40
    assert case["tracking_hash"] == sha256(code) and case["tracking_hash"] != code
    assert case["status"] == "pending"
    assert client.get("/my-case").status_code == 200
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM case_events WHERE case_id=?", (case["id"],)).fetchone()[0] == 1


def test_teacher_access_ignores_hidden_vm_and_class_fields(client, settings):
    case, _ = submit(client, settings, applicant_role="teacher", class_name="MUST NOT BE SAVED", request_type="access",
                     access_scope="Adgang til pool for mit undervisningshold. Start og stop af egne VM’er.", cpu_cores="evil")
    assert case["class_name"] is None
    assert case["cpu_cores"] is None and case["os_family"] is None
    assert case["access_scope"].startswith("Adgang til pool")


@pytest.mark.parametrize("change", [
    {"applicant_role": "admin"}, {"applicant_name": ""}, {"class_name": ""}, {"email": "not-an-email"},
    {"request_type": "root"}, {"title": ""}, {"purpose": "short"}, {"os_family": "bogus"}, {"os_version": ""},
    {"cpu_cores": "0"}, {"cpu_cores": "65"}, {"cpu_cores": "1.5"}, {"ram_gib": "513"}, {"storage_gib": "-10"},
    {"starts_on": "2026-99-99"}, {"acknowledge": ""}, {"request_type": "access", "access_scope": ""},
    {"applicant_name": "x" * 121}, {"purpose": "Test\x00control characters are not allowed"},
])
def test_invalid_submissions_are_not_saved(client, settings, db, change):
    response = client.post("/apply", data=form_data(client, settings, **change))
    assert response.status_code == 422
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 0


def test_period_validation_and_inclusive_day(client, settings):
    today = services.local_today(settings)
    for changes in [
        {"starts_on": (today - timedelta(days=1)).isoformat()},
        {"ends_on": (today - timedelta(days=1)).isoformat()},
        {"ends_on": (today + timedelta(days=730)).isoformat()},
    ]:
        assert client.post("/apply", data=form_data(client, settings, **changes)).status_code == 422
    case, _ = submit(client, settings, ends_on=today.isoformat())
    assert services.enrich(case, today)["duration_days"] == 1


def test_duplicate_submission_is_idempotent(client, settings, db):
    form = form_data(client, settings)
    first = client.post("/apply", data=form)
    second = client.post("/apply", data=form)
    assert first.status_code == 201 and second.status_code == 200
    assert 'id="receipt-code"' in second.text
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM case_events").fetchone()[0] == 1


@pytest.mark.parametrize("token", ["", "not-the-csrf-token", "æøå"])
def test_csrf_rejected(client, settings, token):
    form = form_data(client, settings)
    form["csrf_token"] = token
    assert client.post("/apply", data=form).status_code == 403


def test_cross_origin_form_rejected(client, settings):
    form = form_data(client, settings)
    assert client.post("/apply", data=form, headers={"Origin": "https://attacker.example"}).status_code == 403


def test_valid_origin_and_bad_host(client, settings):
    form = form_data(client, settings)
    assert client.post("/apply", data=form, headers={"Origin": "http://testserver"}).status_code == 201
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400


def test_cross_session_submission_token_rejected(client, app, settings):
    original = form_data(client, settings)
    with TestClient(app) as stranger:
        other = form_data(stranger, settings)
        other["submission_token"] = original["submission_token"]
        assert stranger.post("/apply", data=other).status_code == 403


def test_bad_body_type_size_and_duplicate_fields(client, settings):
    assert client.post("/apply", json={"hello": "world"}).status_code == 415
    assert client.post("/apply", content="x=" + "x" * 33000, headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 413
    assert client.post("/apply", content="x=1&x=2", headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 400


def test_no_admin_access_from_applicant_role(client, settings):
    submit(client, settings, applicant_role="teacher", is_admin="1", status="approved")
    for path in ("/admin", "/admin/cases/1", "/admin/export.csv"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/login"


def test_status_requires_secret_not_case_number(client, app, settings):
    case, code = submit(client, settings)
    with TestClient(app) as other:
        page = other.get("/status")
        csrf = hidden(page.text, "csrf_token")
        denied = other.post("/status", data={"csrf_token": csrf, "case_number": case["case_number"], "tracking_code": "wrong"})
        assert denied.status_code == 403
        assert other.get("/my-case", follow_redirects=False).status_code == 303
        accepted = other.post("/status", data={"csrf_token": csrf, "case_number": case["case_number"], "tracking_code": code})
        assert accepted.status_code == 200 and case["applicant_name"] in accepted.text


def test_admin_login_session_rotation_and_logout(client, settings, admin):
    client.get("/admin/login")
    before = client.cookies.get(COOKIE_NAME)
    login(client, admin)
    assert client.cookies.get(COOKIE_NAME) != before
    page = client.get("/admin")
    assert "Sagsoversigt" in page.text
    result = client.post("/admin/logout", data={"csrf_token": hidden(page.text, "csrf_token")}, follow_redirects=False)
    assert result.status_code == 303
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_wrong_password_and_disabled_admin(client, admin, db):
    page = client.get("/admin/login")
    data = {"csrf_token": hidden(page.text, "csrf_token"), "email": admin["email"], "password": "wrong"}
    assert client.post("/admin/login", data=data).status_code == 403
    with db.write() as conn:
        conn.execute("UPDATE admins SET is_active=0 WHERE id=?", (admin["id"],))
    data["password"] = ADMIN_PASSWORD
    assert client.post("/admin/login", data=data).status_code == 403


def test_approved_is_not_automatically_delivered(client, settings, admin, db):
    case, _ = submit(client, settings)
    login(client, admin)
    assert action(client, case["id"], "approve").status_code == 400
    assert action(client, case["id"], "approve", identity_verified="yes", public_note="Godkendt til projektet.").status_code == 303
    with db.read() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case["id"],)).fetchone()
        assert row["status"] == "approved"
        assert row["assigned_vmid"] is None and row["assigned_node"] == ""
        assert row["identity_verified_by"] == admin["id"]


def test_full_vm_workflow_archive_restore(client, settings, admin, db):
    case, _ = submit(client, settings)
    case_id = case["id"]
    login(client, admin)
    assert action(client, case_id, "review").status_code == 303
    assert action(client, case_id, "approve", identity_verified="yes").status_code == 303
    assert action(client, case_id, "activate").status_code == 400
    assert action(client, case_id, "activate", assigned_node="pve01", assigned_vmid="150", assigned_address="vm150.lab.example.org").status_code == 303
    assert action(client, case_id, "archive", internal_note="Not allowed").status_code == 409
    assert action(client, case_id, "close", public_note="Projektet er afsluttet.").status_code == 400
    assert action(client, case_id, "close", public_note="Projektet er afsluttet.", decommissioned="yes").status_code == 303
    assert action(client, case_id, "archive", internal_note="Projekt afsluttet og VM manuelt afviklet.").status_code == 303
    with db.read() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        assert row["archived_at"] and row["status"] == "closed"
        assert conn.execute("SELECT count(*) FROM case_events WHERE case_id=?", (case_id,)).fetchone()[0] == 6
    assert action(client, case_id, "note", internal_note="Cannot mutate archive").status_code == 409
    assert action(client, case_id, "restore").status_code == 303
    with db.read() as conn:
        assert conn.execute("SELECT archived_at FROM cases WHERE id=?", (case_id,)).fetchone()[0] is None


def test_access_delivery_requires_account(client, settings, admin):
    case, _ = submit(client, settings, applicant_role="teacher", request_type="access", access_scope="Kun adgang til klassens pool og konsoller.")
    login(client, admin)
    assert action(client, case["id"], "approve", identity_verified="yes").status_code == 303
    assert action(client, case["id"], "activate").status_code == 400
    assert action(client, case["id"], "activate", assigned_account="demo@pve").status_code == 303


def test_internal_notes_never_visible_to_applicant(client, settings, admin, app):
    case, code = submit(client, settings)
    login(client, admin)
    assert action(client, case["id"], "note", public_note="Offentlig besked om din sag.", internal_note="PRIVATE ADMIN NOTE 938742").status_code == 303
    with TestClient(app) as applicant:
        page = applicant.get("/status")
        response = applicant.post("/status", data={"csrf_token": hidden(page.text, "csrf_token"), "case_number": case["case_number"], "tracking_code": code})
        assert "Offentlig besked om din sag." in response.text
        assert "PRIVATE ADMIN NOTE" not in response.text
        assert "Demo Administrator" not in response.text


def test_optimistic_concurrency_stops_overwrite(client, settings, admin, db):
    case, _ = submit(client, settings)
    login(client, admin)
    assert action(client, case["id"], "approve", identity_verified="yes").status_code == 303
    response = action(client, case["id"], "review", version="1")
    assert response.status_code == 409
    with db.read() as conn:
        row = conn.execute("SELECT status,version FROM cases WHERE id=?", (case["id"],)).fetchone()
        assert row["status"] == "approved" and row["version"] == 2
        assert conn.execute("SELECT count(*) FROM case_events").fetchone()[0] == 2


def test_rejection_requires_reason_and_may_be_reconsidered(client, settings, admin):
    case, _ = submit(client, settings)
    login(client, admin)
    assert action(client, case["id"], "reject").status_code == 400
    assert action(client, case["id"], "reject", public_note="Der mangler kapacitet.").status_code == 303
    assert action(client, case["id"], "review", public_note="Der er kommet ny kapacitet.").status_code == 303


def test_expiry_and_extension_keep_original_request(client, settings, admin, db):
    case, _ = submit(client, settings)
    login(client, admin)
    action(client, case["id"], "approve", identity_verified="yes")
    original_end = case["ends_on"]
    new_end = (date.fromisoformat(original_end) + timedelta(days=30)).isoformat()
    assert action(client, case["id"], "extend", new_ends_on=new_end, public_note="Projektet fortsætter en måned.").status_code == 303
    with db.read() as conn:
        row = dict(conn.execute("SELECT * FROM cases WHERE id=?", (case["id"],)).fetchone())
    assert row["requested_ends_on"] == original_end and row["ends_on"] == new_end
    assert not services.enrich(row, date.fromisoformat(new_end))["overdue"]
    assert services.enrich(row, date.fromisoformat(new_end) + timedelta(days=1))["overdue"]


def test_history_is_append_only(client, settings, db):
    submit(client, settings)
    for sql in ("UPDATE case_events SET public_note='tamper'", "DELETE FROM case_events"):
        with pytest.raises(sqlite3.IntegrityError):
            with db.write() as conn:
                conn.execute(sql)


def test_unique_case_numbers_under_concurrent_submissions(client, settings, db):
    data, errors = validate_application(valid_data(settings), settings, services.local_today(settings))
    assert not errors
    def create(index):
        return services.submit_case(db, settings, data, f"concurrency-nonce-{index}")[0]["case_number"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(create, range(30)))
    assert len(set(numbers)) == 30
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM case_events").fetchone()[0] == 30


def test_search_pagination_filters_and_csv_formula_escape(client, settings, admin, db):
    submit(client, settings, title="=HYPERLINK(\"example\")", applicant_name="=2+2", class_name="itt-csd-s26")
    for n in range(26):
        data, errors = validate_application(valid_data(settings, title=f"Demo VM nummer {n}"), settings, services.local_today(settings))
        services.submit_case(db, settings, data, f"pagination-{n}")
    login(client, admin)
    listing = client.get("/admin?page=2")
    assert listing.status_code == 200 and "Side 2 af 2" in listing.text
    assert "Ingen sager matcher" in client.get("/admin?q=%27%20OR%201%3D1--").text
    response = client.get("/admin/export.csv")
    assert response.status_code == 200 and response.text.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(response.text.lstrip("\ufeff")), delimiter=";"))
    assert len(rows) == 28
    assert any("'=2+2" in row for row in rows)
    assert "tracking_hash" not in response.text and "submission_key" not in response.text


def test_html_is_escaped(client, settings, admin):
    case, _ = submit(client, settings, title="<script>alert('xss')</script>")
    login(client, admin)
    page = client.get(f"/admin/cases/{case['id']}")
    assert "<script>alert('xss')</script>" not in page.text
    assert "&lt;script&gt;" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]


def test_backup_integrity_and_migration_are_non_destructive(client, settings, db, tmp_path):
    case, _ = submit(client, settings)
    backup = tmp_path / "backup.sqlite3"
    db.backup(backup)
    restored = Database(backup)
    restored.migrate()
    restored.migrate()
    with restored.read() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT case_number FROM cases").fetchone()[0] == case["case_number"]
        assert conn.execute("SELECT count(*) FROM web_sessions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
    with pytest.raises(FileExistsError):
        db.backup(backup)


def test_rate_limit_is_shared_and_does_not_store_raw_identity(client, settings, db):
    assert rate_limit(db, settings, "test", "192.0.2.5", 2, 60)
    assert rate_limit(db, settings, "test", "192.0.2.5", 2, 60)
    assert not rate_limit(db, settings, "test", "192.0.2.5", 2, 60)
    with db.read() as conn:
        row = conn.execute("SELECT bucket_key,hits FROM rate_limits WHERE hits=3").fetchone()
        assert "192.0.2.5" not in row["bucket_key"] and len(row["bucket_key"]) == 64


def test_login_rate_limit(settings, admin_hash):
    app = create_app(replace(settings, login_ip_limit=2))
    with TestClient(app) as client:
        page = client.get("/admin/login")
        data = {"csrf_token": hidden(page.text, "csrf_token"), "email": "wrong@example.org", "password": "wrong"}
        assert client.post("/admin/login", data=data).status_code == 403
        assert client.post("/admin/login", data=data).status_code == 403
        assert client.post("/admin/login", data=data).status_code == 429


def test_server_side_sessions_expire(client, settings, admin, db):
    login(client, admin)
    with db.write() as conn:
        conn.execute("UPDATE web_sessions SET expires_at=0")
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_disabling_admin_revokes_access_on_next_request(client, admin, db):
    login(client, admin)
    with db.write() as conn:
        conn.execute("UPDATE admins SET is_active=0 WHERE id=?", (admin["id"],))
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_security_headers_and_cookie(client):
    response = client.get("/")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_https_production_cookie(settings):
    settings = replace(settings, environment="production", secure_cookies=True, public_base_url="https://testserver")
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.get("/")
        assert "Secure" in response.headers["set-cookie"]
        assert response.headers["strict-transport-security"] == "max-age=31536000"


@pytest.mark.parametrize("changes", [
    {"secret_key": "short"}, {"environment": "production"}, {"allowed_hosts": ("*",)},
    {"public_base_url": "javascript:alert(1)"}, {"public_base_url": "http://testserver/subpath"}, {"max_vcpu": 0},
])
def test_invalid_configuration_is_rejected(settings, changes):
    with pytest.raises(ValueError):
        replace(settings, **changes)


def test_email_domain_restriction_is_enforced(settings):
    settings = replace(settings, allowed_email_domains=("ucn.dk",))
    data, errors = validate_application(valid_data(settings), settings, services.local_today(settings))
    assert "email" in errors


def test_password_hashing_policy(admin_hash):
    assert admin_hash.startswith("$argon2id$")
    assert verify_password(ADMIN_PASSWORD, admin_hash)
    assert not verify_password("wrong password", admin_hash)
    with pytest.raises(ValueError):
        hash_password("short")
