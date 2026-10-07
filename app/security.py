# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Opaque server-side sessions, CSRF helpers and database-backed rate limits."""
import base64
import hashlib
import hmac
import ipaddress
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .config import Settings
from .db import Database

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
# A randomized dummy hash prevents a fast "unknown email" branch at login.
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
COOKIE_NAME = "labportalen_session"


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    if not 14 <= len(password) <= 128:
        raise ValueError("Adgangskoden skal indeholde mellem 14 og 128 tegn.")
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not isinstance(password, str) or len(password) > 128:
        return False
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass
class Session:
    token_hash: str
    csrf_token: str
    expires_at: int
    admin_id: int | None = None
    status_case_id: int | None = None
    new_token: str | None = None


class Sessions:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def create(self, admin_id=None, status_case_id=None, replacing=None) -> Session:
        token = secrets.token_urlsafe(32)
        sess = Session(sha256(token), secrets.token_urlsafe(32), int(time.time()) + self.settings.session_seconds,
                       admin_id, status_case_id, token)
        with self.db.write() as conn:
            if replacing:
                conn.execute("DELETE FROM web_sessions WHERE token_hash=?", (replacing,))
            conn.execute("INSERT INTO web_sessions(token_hash,csrf_token,admin_id,status_case_id,expires_at) VALUES (?,?,?,?,?)",
                         (sess.token_hash, sess.csrf_token, admin_id, status_case_id, sess.expires_at))
            conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (int(time.time()),))
        return sess

    def load(self, token: str | None) -> Session:
        if token and len(token) <= 128:
            with self.db.read() as conn:
                row = conn.execute("SELECT * FROM web_sessions WHERE token_hash=? AND expires_at>?",
                                   (sha256(token), int(time.time()))).fetchone()
                if row:
                    return Session(**dict(row))
        return self.create()

    def destroy(self, sess: Session):
        with self.db.write() as conn:
            conn.execute("DELETE FROM web_sessions WHERE token_hash=?", (sess.token_hash,))

    def grant_status(self, sess: Session, case_id: int):
        with self.db.write() as conn:
            conn.execute("UPDATE web_sessions SET status_case_id=? WHERE token_hash=?", (case_id, sess.token_hash))
        sess.status_case_id = case_id


def issue_submission(settings: Settings, sess: Session) -> str:
    serializer = URLSafeTimedSerializer(settings.secret_key, salt="application-v1")
    return serializer.dumps({"sid": sess.token_hash, "nonce": secrets.token_urlsafe(32)})


def verify_submission(settings: Settings, sess: Session, token: str) -> str:
    try:
        data = URLSafeTimedSerializer(settings.secret_key, salt="application-v1").loads(token, max_age=settings.session_seconds)
        if not isinstance(data, dict) or not isinstance(data.get("sid"), str) or not isinstance(data.get("nonce"), str):
            raise ValueError
        if not hmac.compare_digest(data["sid"], sess.token_hash) or len(data["nonce"]) != 43:
            raise ValueError
        return data["nonce"]
    except (BadSignature, SignatureExpired, ValueError, KeyError, TypeError):
        raise ValueError("Formularen er udløbet. Åbn en ny ansøgning og prøv igen.") from None


def tracking_code(settings: Settings, nonce: str) -> str:
    # Repeat submissions receive the same receipt without storing its secret in clear text.
    digest = hmac.new(settings.secret_key.encode(), b"tracking-v1:" + nonce.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def client_ip(request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    # Trust exactly configured peers only; never trust client-supplied X-Forwarded-For.
    if peer in settings.trusted_proxy_ips:
        forwarded = request.headers.get("x-real-ip", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer


def rate_limit(db: Database, settings: Settings, scope: str, identity: str, maximum: int, seconds: int) -> bool:
    """Return True when this request is allowed. Counters are shared across processes."""
    now = int(time.time())
    start = now - now % seconds
    key = hmac.new(settings.secret_key.encode(), f"{scope}:{identity}".encode(), hashlib.sha256).hexdigest()
    with db.write() as conn:
        conn.execute("DELETE FROM rate_limits WHERE expires_at < ?", (now,))
        conn.execute("""INSERT INTO rate_limits(bucket_key,window_start,hits,expires_at) VALUES (?,?,1,?)
                        ON CONFLICT(bucket_key,window_start) DO UPDATE SET hits=hits+1""", (key, start, start + seconds))
        hits = conn.execute("SELECT hits FROM rate_limits WHERE bucket_key=? AND window_start=?", (key, start)).fetchone()[0]
    return hits <= maximum
