# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Server-side validation; browser constraints are only a convenience."""
from datetime import date
from email_validator import validate_email, EmailNotValidError

ROLES = {"student": "Studerende", "teacher": "Underviser"}
REQUEST_TYPES = {"vm": "Virtuel maskine", "access": "Adgang til Proxmox"}
OS_FAMILIES = {
    "debian": "Debian", "ubuntu": "Ubuntu", "windows_server": "Windows Server",
    "windows": "Windows", "kali": "Kali Linux", "other": "Andet operativsystem",
}
STATUSES = {
    "pending": "Modtaget", "review": "Under behandling", "approved": "Godkendt",
    "active": "Leveret / aktiv", "rejected": "Afvist", "closed": "Afsluttet",
}
ACTIONS = {
    "submitted": "Ansøgning modtaget", "review": "Behandling startet", "approve": "Godkendt",
    "reject": "Afvist", "activate": "Levering registreret", "close": "Sag afsluttet",
    "archive": "Arkiveret", "restore": "Hentet fra arkiv", "note": "Notat tilføjet",
    "extend": "Tildelingsperiode forlænget", "status_code_reset": "Privat statuskode fornyet",
}


def text(value, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("Feltet skal være tekst.")
    value = value.strip().replace("\r\n", "\n")
    if len(value) > maximum:
        raise ValueError(f"Maksimalt {maximum} tegn.")
    if any(ord(c) < 32 and c not in {"\n", "\t"} for c in value):
        raise ValueError("Feltet indeholder ugyldige kontroltegn.")
    return value


def normalize_email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False, allow_smtputf8=False).normalized.lower()
    except (EmailNotValidError, AttributeError):
        raise ValueError("Indtast en gyldig e-mailadresse.") from None


def validate_application(form: dict, settings, today: date):
    data, errors = {}, {}

    def field(name, maximum, minimum=0):
        try:
            value = text(form.get(name, ""), maximum)
            if len(value) < minimum:
                raise ValueError("Udfyld dette felt." if minimum <= 1 else f"Skriv mindst {minimum} tegn.")
            data[name] = value
        except ValueError as exc:
            errors[name] = str(exc)
            data[name] = ""

    for name, choices in (("applicant_role", ROLES), ("request_type", REQUEST_TYPES)):
        data[name] = form.get(name, "")
        if data[name] not in choices:
            errors[name] = "Vælg en af mulighederne."
    field("applicant_name", 120, 2)
    if data["applicant_role"] == "student":
        field("class_name", 60, 1)
    else:
        data["class_name"] = None
    try:
        data["email"] = normalize_email(form.get("email", ""))
        domain = data["email"].split("@")[-1]
        if settings.allowed_email_domains and domain not in settings.allowed_email_domains:
            raise ValueError("Brug en e-mailadresse fra: " + ", ".join(settings.allowed_email_domains))
    except ValueError as exc:
        errors["email"] = str(exc)
    field("title", 160, 3)
    field("purpose", 4000, 10)
    data.update(os_family=None, os_version=None, cpu_cores=None, ram_gib=None, storage_gib=None, access_scope=None)
    if data["request_type"] == "vm":
        data["os_family"] = form.get("os_family", "")
        if data["os_family"] not in OS_FAMILIES:
            errors["os_family"] = "Vælg et operativsystem."
        field("os_version", 120, 1)
        for name, maximum in (("cpu_cores", settings.max_vcpu), ("ram_gib", settings.max_ram_gib),
                              ("storage_gib", settings.max_storage_gib)):
            try:
                raw = form.get(name, "")
                if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit():
                    raise ValueError
                value = int(raw)
                if not 1 <= value <= maximum:
                    raise ValueError
                data[name] = value
            except (ValueError, TypeError):
                errors[name] = f"Angiv et heltal mellem 1 og {maximum}."
    elif data["request_type"] == "access":
        field("access_scope", 2000, 10)
    dates = {}
    for name in ("starts_on", "ends_on"):
        try:
            dates[name] = date.fromisoformat(form.get(name, ""))
            if dates[name].isoformat() != form.get(name, ""):
                raise ValueError
            data[name] = dates[name].isoformat()
        except (ValueError, TypeError):
            errors[name] = "Angiv en gyldig dato."
    if "starts_on" in dates and dates["starts_on"] < today:
        errors["starts_on"] = "Startdatoen må ikke ligge før i dag."
    if len(dates) == 2:
        duration = (dates["ends_on"] - dates["starts_on"]).days + 1
        if duration < 1:
            errors["ends_on"] = "Slutdatoen må ikke ligge før startdatoen."
        elif duration > settings.max_duration_days:
            errors["ends_on"] = f"Perioden må højst være {settings.max_duration_days} dage inklusive begge datoer."
    if form.get("acknowledge") != "yes":
        errors["acknowledge"] = "Bekræft, at oplysningerne er korrekte, og at du har læst informationen."
    return data, errors
