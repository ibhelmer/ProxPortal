# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for group membership and applicant-controlled lease requests."""
from datetime import timedelta
import re
from conftest import submit, login, action, hidden, form_data
from app.services import local_today, case_by_id


def authorize_status(client, case, code):
    page = client.get("/status")
    reply = client.post("/status", data={"csrf_token": hidden(page.text, "csrf_token"),
        "case_number": case["case_number"], "tracking_code": code}, follow_redirects=False)
    assert reply.status_code == 303


def ask_extension(client, settings, days=110):
    page = client.get("/my-case")
    return client.post("/my-case/lease", data={"csrf_token": hidden(page.text, "csrf_token"),
        "new_ends_on": (local_today(settings) + timedelta(days=days)).isoformat(),
        "reason": "Projektet fortsætter efter første periode."}, follow_redirects=False)


def decide_extension(client, case, decision, message):
    page = client.get(f"/admin/cases/{case['id']}")
    match = re.search(r'name="lease_id" value="(\d+)"', page.text)
    assert match, page.text
    return client.post(f"/admin/cases/{case['id']}/lease", data={
        "csrf_token": hidden(page.text, "csrf_token"),
        "version": hidden(page.text, "version"),
        "lease_id": match.group(1), "decision": decision, "decision_note": message
    }, follow_redirects=False)


def test_about_and_guidelines_are_explicitly_draft(client):
    assert "Om portalen og regler" in client.get("/").text
    page = client.get("/about")
    assert page.status_code == 200
    assert "ikke officielt vedtagne UCN-regler" in page.text
    assert "Send ansøgning om forlængelse" in page.text


def test_multiple_students_are_saved_and_visible(client, settings, db):
    case, code = submit(client, settings, additional_students=(
        "Anna Jensen; ANNA@example.org; itt-csd-s26\n"
        "Bo Hansen; bo@example.org; itt-csd-s25"
    ))
    loaded, _ = case_by_id(db, case["id"], local_today(settings))
    assert len(loaded["participants"]) == 2
    assert loaded["participants"][0]["student_email"] == "anna@example.org"
    assert "Anna Jensen" in client.get("/my-case").text


def test_participant_input_is_validated(client, settings, db):
    invalid = [
        "A; a@example.org; itt",
        "Anna Jensen; student@example.org; itt",
        "Anna Jensen; notanemail; itt",
        "Anna Jensen; a@example.org; itt\nBo Hansen; A@example.org; itt",
        "\n".join(f"Student {n}; student{n}@example.org; itt" for n in range(16)),
    ]
    for entry in invalid:
        reply = client.post("/apply", data=form_data(client, settings, additional_students=entry))
        assert reply.status_code == 422
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM cases").fetchone()[0] == 0


def test_only_a_status_authorized_applicant_can_request_extension(client, settings, db):
    case, code = submit(client, settings)
    page = client.get("/status")
    deny = client.post("/my-case/lease", data={
        "csrf_token": hidden(page.text, "csrf_token"),
        "new_ends_on": "2027-12-31", "reason": "Extra project period",
    })
    # The submitter's original receipt session has case access; check a separate client for denial instead.
    from fastapi.testclient import TestClient
    with TestClient(client.app) as stranger:
        page = stranger.get("/status")
        response = stranger.post("/my-case/lease", data={
            "csrf_token": hidden(page.text, "csrf_token"),
            "new_ends_on": "2027-12-31", "reason": "Extra project period",
        })
        assert response.status_code == 403
    assert ask_extension(client, settings).status_code == 409  # Not approved yet


def test_admin_approves_extension_without_changing_original_request(client, settings, db, admin):
    case, code = submit(client, settings)
    login(client, admin)
    authorize_status(client, case, code)
    assert action(client, case["id"], "approve", identity_verified="yes").status_code == 303
    original = case["ends_on"]
    assert ask_extension(client, settings).status_code == 303
    loaded, events = case_by_id(db, case["id"], local_today(settings))
    assert loaded["ends_on"] == original
    assert loaded["pending_lease"]
    assert ask_extension(client, settings).status_code == 409
    assert "Forlængelse afventer" in client.get("/admin").text
    assert action(client, case["id"], "close", public_note="Afsluttet", decommissioned="yes").status_code == 409
    assert decide_extension(client, case, "approve", "Godkendt forlængelse.").status_code == 303
    loaded, events = case_by_id(db, case["id"], local_today(settings))
    assert loaded["pending_lease"] is None
    assert loaded["lease_requests"][0]["status"] == "approved"
    assert loaded["ends_on"] > original
    assert loaded["requested_ends_on"] == original
    assert any(item["action"] == "lease_approved" for item in events)


def test_admin_can_reject_extension_without_changing_date(client, settings, db, admin):
    case, code = submit(client, settings)
    login(client, admin)
    authorize_status(client, case, code)
    action(client, case["id"], "approve", identity_verified="yes")
    assert ask_extension(client, settings).status_code == 303
    assert decide_extension(client, case, "reject", "Begrænset kapacitet.").status_code == 303
    loaded, _ = case_by_id(db, case["id"], local_today(settings))
    assert loaded["ends_on"] == case["ends_on"]
    assert loaded["lease_requests"][0]["status"] == "rejected"
    assert ask_extension(client, settings, 125).status_code == 303


def test_two_migrations_keep_old_case(client, settings, db):
    case, _ = submit(client, settings)
    db.migrate()
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2
        assert conn.execute("SELECT case_number FROM cases WHERE id=?", (case["id"],)).fetchone()[0] == case["case_number"]
