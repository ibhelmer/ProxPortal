# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Validated configuration. No administrator or secret is created implicitly."""
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_path: Path = Path("data/labportalen.sqlite3")
    environment: str = "development"
    public_base_url: str = "http://127.0.0.1:8000"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost")
    trusted_proxy_ips: tuple[str, ...] = ()
    secure_cookies: bool = False
    organization: str = "UCN"
    portal_name: str = "ProxPortal"
    support_email: str = ""
    privacy_url: str = ""
    allowed_email_domains: tuple[str, ...] = ()
    max_vcpu: int = 64
    max_ram_gib: int = 512
    max_storage_gib: int = 8192
    max_duration_days: int = 730
    session_seconds: int = 7200
    submit_ip_limit: int = 120
    submit_email_limit: int = 5
    login_ip_limit: int = 10
    status_ip_limit: int = 60
    page_size: int = 25
    max_form_bytes: int = 32768
    timezone: str = "Europe/Copenhagen"

    def __post_init__(self):
        if len(self.secret_key) < 32 or self.secret_key.startswith("CHANGE_ME"):
            raise ValueError("SECRET_KEY skal være mindst 32 tilfældige tegn. Kør scripts/setup_env.py.")
        parsed = urlsplit(self.public_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("PUBLIC_BASE_URL skal være en gyldig http(s)-adresse uden login.")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("PUBLIC_BASE_URL må ikke indeholde en sti, query eller fragment.")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS skal indeholde konkrete værtsnavne.")
        if parsed.hostname not in self.allowed_hosts:
            raise ValueError("Værtsnavnet i PUBLIC_BASE_URL skal stå i ALLOWED_HOSTS.")
        if self.environment not in {"development", "production", "test"}:
            raise ValueError("APP_ENV skal være development, production eller test.")
        if self.environment == "production" and (parsed.scheme != "https" or not self.secure_cookies):
            raise ValueError("Produktion kræver HTTPS i PUBLIC_BASE_URL og SECURE_COOKIES=1.")
        if self.privacy_url and urlsplit(self.privacy_url).scheme not in {"https", "http"}:
            raise ValueError("PRIVACY_URL skal være en http(s)-adresse.")
        for value in (self.max_vcpu, self.max_ram_gib, self.max_storage_gib,
                      self.max_duration_days, self.session_seconds, self.submit_ip_limit,
                      self.submit_email_limit, self.login_ip_limit, self.status_ip_limit):
            if value < 1:
                raise ValueError("Grænser og tidsfrister skal være positive heltal.")

    @classmethod
    def from_env(cls):
        load_dotenv()
        csv = lambda key, default="": tuple(v.strip().lower() for v in os.getenv(key, default).split(",") if v.strip())
        integer = lambda key, default: int(os.getenv(key, str(default)))
        return cls(
            secret_key=os.getenv("SECRET_KEY", ""),
            database_path=Path(os.getenv("DATABASE_PATH", "data/labportalen.sqlite3")),
            environment=os.getenv("APP_ENV", "development"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            allowed_hosts=csv("ALLOWED_HOSTS", "127.0.0.1,localhost"),
            trusted_proxy_ips=csv("TRUSTED_PROXY_IPS"),
            secure_cookies=os.getenv("SECURE_COOKIES", "0") == "1",
            organization=os.getenv("ORGANIZATION", "UCN"),
            portal_name=os.getenv("PORTAL_NAME", "ProxPortal"),
            support_email=os.getenv("SUPPORT_EMAIL", ""),
            privacy_url=os.getenv("PRIVACY_URL", ""),
            allowed_email_domains=csv("ALLOWED_EMAIL_DOMAINS"),
            max_vcpu=integer("MAX_VCPU", 64), max_ram_gib=integer("MAX_RAM_GIB", 512),
            max_storage_gib=integer("MAX_STORAGE_GIB", 8192),
            max_duration_days=integer("MAX_DURATION_DAYS", 730),
            submit_ip_limit=integer("SUBMIT_IP_LIMIT", 120),
            submit_email_limit=integer("SUBMIT_EMAIL_LIMIT", 5),
            login_ip_limit=integer("LOGIN_IP_LIMIT", 10),
            status_ip_limit=integer("STATUS_IP_LIMIT", 60),
        )
