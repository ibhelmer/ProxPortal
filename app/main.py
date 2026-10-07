# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Danish HTML portal. Run with: uvicorn app.main:create_app --factory."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo
import hmac
import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Settings
from .db import Database
from .security import COOKIE_NAME, Sessions, client_ip, issue_submission, rate_limit, verify_submission
from .validation import ROLES, REQUEST_TYPES, OS_FAMILIES, STATUSES, ACTIONS, validate_application
from . import services

logger = logging.getLogger("labportalen")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)
    sessions = Sessions(db, settings)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(db.migrate)
        yield

    app = FastAPI(title=settings.portal_name, version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.db, app.state.sessions = settings, db, sessions

    def format_date(value):
        if not value:
            return "—"
        try:
            if "T" in str(value):
                return datetime.fromisoformat(value).astimezone(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y kl. %H:%M")
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        except ValueError:
            return str(value)

    templates.env.filters["dkdate"] = format_date
    templates.env.globals.update(roles=ROLES, request_types=REQUEST_TYPES, os_families=OS_FAMILIES,
                                 statuses=STATUSES, actions=ACTIONS, version=__version__, settings=settings)

    def render(request, name, context=None, status_code=200):
        sess = getattr(request.state, "session", None)
        base = {"csrf": sess.csrf_token if sess else "", "admin": getattr(request.state, "admin", None),
                "today": services.local_today(settings), "page_title": settings.portal_name}
        base.update(context or {})
        return templates.TemplateResponse(request=request, name=name, context=base, status_code=status_code)

    def error(request, message, status=400):
        return render(request, "error.html", {"message": message, "error_code": status}, status)

    def limit(request, scope, maximum, seconds, identity=None):
        return rate_limit(db, settings, scope, identity or client_ip(request, settings), maximum, seconds)

    @app.middleware("http")
    async def portal_security(request: Request, call_next):
        # Static assets and health checks do not create database sessions.
        needs_session = not request.url.path.startswith("/static/") and request.url.path not in {"/healthz", "/favicon.ico"}
        response = None
        if needs_session:
            request.state.session = await run_in_threadpool(sessions.load, request.cookies.get(COOKIE_NAME))
            request.state.admin = await run_in_threadpool(services.get_admin, db, request.state.session.admin_id)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not needs_session:
                response = error(request, "Metoden er ikke tilladt.", 405)
            elif request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
                response = error(request, "Kun almindelige webformularer accepteres.", 415)
            else:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > settings.max_form_bytes:
                        response = error(request, "Formularen er for stor.", 413)
                        break
                if response is None:
                    try:
                        values = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True,
                                          max_num_fields=48, encoding="utf-8", errors="strict")
                        if any(len(v) != 1 for v in values.values()):
                            raise ValueError("Duplicate fields")
                        request.state.form = {k: v[0] for k, v in values.items()}
                    except (UnicodeError, ValueError):
                        response = error(request, "Formularen kunne ikke læses.", 400)
                if response is None:
                    posted = request.state.form.get("csrf_token", "")
                    expected = request.state.session.csrf_token
                    if not hmac.compare_digest(posted.encode(), expected.encode()):
                        response = error(request, "Sikkerhedskontrollen udløb eller fejlede. Genindlæs siden og prøv igen.", 403)
                    origin = request.headers.get("origin")
                    if origin and origin != settings.public_base_url.rstrip("/"):
                        response = error(request, "Formularen blev sendt fra en anden adresse end portalens adresse.", 403)
        if response is None:
            response = await call_next(request)
        if needs_session:
            sess = request.state.session
            if getattr(request.state, "clear_cookie", False):
                response.delete_cookie(COOKIE_NAME, path="/", secure=settings.secure_cookies, httponly=True, samesite="lax")
            elif sess.new_token:
                response.set_cookie(COOKIE_NAME, sess.new_token, max_age=settings.session_seconds, path="/",
                                    secure=settings.secure_cookies, httponly=True, samesite="lax")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if not request.url.path.startswith("/static/") and request.url.path != "/favicon.ico":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts), www_redirect=False)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.exception_handler(services.CaseError)
    async def case_error(request, exc):
        return error(request, exc.message, exc.status_code)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        messages = {404: "Siden findes ikke.", 405: "Metoden er ikke tilladt.", 403: "Du har ikke adgang til denne side."}
        return error(request, messages.get(exc.status_code, "Anmodningen kunne ikke gennemføres."), exc.status_code)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        logger.exception("Database operation failed")
        return error(request, "Databasen er midlertidigt utilgængelig. Forsøg igen; en allerede modtaget ansøgning oprettes ikke dobbelt ved samme genforsøg.", 503)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(Path(__file__).parent / "static" / "favicon.ico",
                            media_type="image/x-icon",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/healthz")
    def health():
        with db.read() as conn:
            conn.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
        return {"status": "ok", "version": __version__}

    @app.get("/")
    def index(request: Request):
        return render(request, "index.html")

    @app.get("/about")
    def about(request: Request):
        return render(request, "about.html", {"page_title": "Om portalen"})

    @app.get("/privacy")
    def privacy(request: Request):
        return render(request, "privacy.html", {"page_title": "Oplysninger og privatliv"})

    @app.get("/apply")
    def application_form(request: Request):
        today = services.local_today(settings)
        values = {"applicant_role": "student", "request_type": "vm", "cpu_cores": "2", "ram_gib": "4", "storage_gib": "40",
                  "starts_on": today.isoformat(), "ends_on": (today + timedelta(days=89)).isoformat()}
        return render(request, "apply.html", {"values": values, "errors": {}, "submission_token": issue_submission(settings, request.state.session),
                                              "page_title": "Ny ansøgning"})

    @app.post("/apply")
    def application_submit(request: Request):
        form = request.state.form
        if not limit(request, "submit-ip", settings.submit_ip_limit, 3600):
            return error(request, "Der er sendt mange ansøgninger fra denne forbindelse. Prøv senere eller kontakt administratoren.", 429)
        try:
            nonce = verify_submission(settings, request.state.session, form.get("submission_token", ""))
        except ValueError as exc:
            return error(request, str(exc), 403)
        data, errors = validate_application(form, settings, services.local_today(settings))
        if errors:
            return render(request, "apply.html", {"values": form, "errors": errors, "submission_token": form.get("submission_token", ""),
                                                  "page_title": "Ret ansøgningen"}, 422)
        if not limit(request, "submit-email", settings.submit_email_limit, 3600, data["email"]):
            return error(request, "Der er allerede sendt flere ansøgninger med denne e-mailadresse. Prøv senere eller kontakt administratoren.", 429)
        case, code, created = services.submit_case(db, settings, data, nonce)
        sessions.grant_status(request.state.session, case["id"])
        return render(request, "receipt.html", {"case": services.enrich(case, services.local_today(settings)), "tracking_code": code,
                                               "page_title": "Ansøgning modtaget"}, 201 if created else 200)

    @app.get("/status")
    def status_form(request: Request):
        return render(request, "status_login.html", {"values": {}, "message": "", "page_title": "Følg din sag"})

    @app.post("/status")
    def status_lookup(request: Request):
        form = request.state.form
        if not limit(request, "status", settings.status_ip_limit, 900):
            return error(request, "For mange opslag. Prøv igen senere.", 429)
        number = form.get("case_number", "").strip()[:40]
        code = form.get("tracking_code", "").strip()[:128]
        case_id = services.find_status_case(db, number, code)
        if not case_id:
            return render(request, "status_login.html", {"values": {"case_number": number}, "message": "Sagsnummer eller privat kode er forkert.",
                                                        "page_title": "Følg din sag"}, 403)
        # Rotate the opaque session when a new case access privilege is granted.
        request.state.session = sessions.create(admin_id=request.state.session.admin_id, status_case_id=case_id,
                                                replacing=request.state.session.token_hash)
        return RedirectResponse("/my-case", status_code=303)

    @app.get("/my-case")
    def my_case(request: Request):
        if not request.state.session.status_case_id:
            return RedirectResponse("/status", status_code=303)
        case, events = services.case_by_id(db, request.state.session.status_case_id, services.local_today(settings))
        public_events = [e for e in events if e["public_note"] or e["action"] in {"submitted", "review", "approve", "reject", "activate", "close", "extend"}]
        return render(request, "my_case.html", {"case": case, "events": public_events, "page_title": case["case_number"]})

    @app.post("/status/forget")
    def forget_status(request: Request):
        sessions.grant_status(request.state.session, None)
        return RedirectResponse("/status", status_code=303)

    @app.get("/admin/login")
    def login_form(request: Request):
        if request.state.admin:
            return RedirectResponse("/admin", status_code=303)
        return render(request, "login.html", {"message": "", "email": "", "page_title": "Administratorlogin"})

    @app.post("/admin/login")
    def login(request: Request):
        form = request.state.form
        email = form.get("email", "").strip().lower()[:254]
        allowed = limit(request, "login-ip", settings.login_ip_limit, 900)
        allowed_email = limit(request, "login-email", 20, 900, email)
        if not allowed or not allowed_email:
            return error(request, "For mange loginforsøg. Prøv igen om op til 15 minutter.", 429)
        actor = services.authenticate(db, email, form.get("password", ""))
        if not actor:
            return render(request, "login.html", {"message": "E-mail eller adgangskode er forkert.", "email": email,
                                                   "page_title": "Administratorlogin"}, 403)
        request.state.session = sessions.create(admin_id=actor["id"], replacing=request.state.session.token_hash)
        return RedirectResponse("/admin", status_code=303)

    @app.post("/admin/logout")
    def logout(request: Request):
        sessions.destroy(request.state.session)
        request.state.clear_cookie = True
        return RedirectResponse("/", status_code=303)

    @app.get("/admin")
    def admin_dashboard(request: Request):
        if not request.state.admin:
            return RedirectResponse("/admin/login", status_code=303)
        listing = services.list_cases(db, settings, dict(request.query_params))
        stats, resources = services.dashboard_stats(db, settings)
        base_query = {k: v for k, v in listing["filters"].items() if v}
        listing.update(stats=stats, resources=resources, export_query=urlencode(base_query),
                       prev_url="/admin?" + urlencode({**base_query, "page": listing["page"] - 1}),
                       next_url="/admin?" + urlencode({**base_query, "page": listing["page"] + 1}),
                       page_title="Administrator · Sagsoversigt")
        return render(request, "dashboard.html", listing)

    @app.get("/admin/export.csv")
    def admin_export(request: Request):
        if not request.state.admin:
            return RedirectResponse("/admin/login", status_code=303)
        result = services.list_cases(db, settings, dict(request.query_params), export=True)
        with db.write() as conn:
            conn.execute("INSERT INTO admin_events(actor_id,action,description,created_at) VALUES (?,?,?,?)",
                         (request.state.admin["id"], "csv_export", f"Eksporterede {result['total']} sager", services.now_iso()))
        return Response(services.export_csv(result["cases"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="labportalen-sager.csv"'})

    @app.get("/admin/cases/{case_id}")
    def admin_case(request: Request, case_id: int):
        if not request.state.admin:
            return RedirectResponse("/admin/login", status_code=303)
        case, events = services.case_by_id(db, case_id, services.local_today(settings))
        done = request.query_params.get("done", "")
        return render(request, "case.html", {"case": case, "events": events, "message": ACTIONS.get(done, ""),
                                             "form_values": {}, "form_error": "", "page_title": case["case_number"]})

    @app.post("/admin/cases/{case_id}/action")
    def admin_action(request: Request, case_id: int):
        if not request.state.admin:
            return error(request, "Log ind som administrator for at behandle sagen.", 403)
        try:
            services.change_case(db, settings, case_id, request.state.admin, request.state.form)
        except services.CaseError as exc:
            if exc.status_code == 404:
                raise
            case, events = services.case_by_id(db, case_id, services.local_today(settings))
            # A concurrency conflict must be acknowledged by reloading, not silently overwritten.
            return render(request, "case.html", {"case": case, "events": events, "message": "",
                                                 "form_values": request.state.form, "form_error": exc.message,
                                                 "conflict": exc.status_code == 409, "page_title": case["case_number"]}, exc.status_code)
        return RedirectResponse(f"/admin/cases/{case_id}?done=" + request.state.form["action"], status_code=303)

    return app
