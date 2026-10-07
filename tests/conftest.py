# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace
from datetime import timedelta
import re
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.security import hash_password
from app.services import local_today, now_iso

ADMIN_PASSWORD = "Only-a-test-password-2026!"

@pytest.fixture(scope="session")
def admin_hash():
    return hash_password(ADMIN_PASSWORD)

@pytest.fixture
def settings(tmp_path):
    return Settings(secret_key="test-only-secret-" * 4, database_path=tmp_path / "portal.sqlite3",
                    environment="test", public_base_url="http://testserver", allowed_hosts=("testserver",),
                    submit_ip_limit=200, submit_email_limit=100)

@pytest.fixture
def app(settings):
    return create_app(settings)

@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client

@pytest.fixture
def db(client, app):
    return app.state.db

@pytest.fixture
def admin(db, admin_hash):
    with db.write() as conn:
        cur = conn.execute("INSERT INTO admins(email,name,password_hash,created_at) VALUES (?,?,?,?)",
                           ("admin@example.org", "Demo Administrator", admin_hash, now_iso()))
        return {"id": cur.lastrowid, "email": "admin@example.org", "name": "Demo Administrator"}


def hidden(html, name):
    match = re.search(r'name="' + re.escape(name) + r'" value="([^"]*)"', html)
    if not match:
        raise AssertionError(f"Hidden field missing: {name}")
    return match.group(1)


def valid_data(settings, **overrides):
    today = local_today(settings)
    data = {"applicant_role": "student", "applicant_name": "Demo Student", "class_name": "itt-csd-s26",
            "email": "student@example.org", "request_type": "vm", "title": "Server til netværksprojekt",
            "purpose": "En virtuel maskine til vores netværksprojekt i undervisningen.", "os_family": "debian",
            "os_version": "13, serverudgave", "cpu_cores": "2", "ram_gib": "4", "storage_gib": "40",
            "starts_on": today.isoformat(), "ends_on": (today + timedelta(days=89)).isoformat(), "acknowledge": "yes"}
    data.update(overrides)
    return data


def form_data(client, settings, **overrides):
    r = client.get("/apply")
    return {**valid_data(settings, **overrides), "csrf_token": hidden(r.text, "csrf_token"),
            "submission_token": hidden(r.text, "submission_token")}


def submit(client, settings, **overrides):
    response = client.post("/apply", data=form_data(client, settings, **overrides))
    assert response.status_code == 201, response.text
    code = re.search(r'id="receipt-code" value="([^"]+)"', response.text).group(1)
    number = re.search(r'id="receipt-number">([^<]+)', response.text).group(1)
    with client.app.state.db.read() as conn:
        case = dict(conn.execute("SELECT * FROM cases WHERE case_number=?", (number,)).fetchone())
    return case, code


def login(client, admin):
    page = client.get("/admin/login")
    response = client.post("/admin/login", data={"csrf_token": hidden(page.text, "csrf_token"),
                                                "email": admin["email"], "password": ADMIN_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return response


def action(client, case_id, action_name, **values):
    page = client.get(f"/admin/cases/{case_id}")
    data = {"csrf_token": hidden(page.text, "csrf_token"), "version": hidden(page.text, "version"), "action": action_name}
    data.update(values)
    return client.post(f"/admin/cases/{case_id}/action", data=data, follow_redirects=False)
