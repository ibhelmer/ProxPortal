#!/usr/bin/env python3
# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
"""Create a local .env with a cryptographic secret; never overwrite an existing file."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
source = root / ".env.example"
target = root / ".env"
if target.exists():
    raise SystemExit(".env findes allerede og er ikke ændret. Redigér den manuelt ved behov.")
content = source.read_text(encoding="utf-8").replace("CHANGE_ME_GENERATE_A_RANDOM_SECRET", secrets.token_hex(32))
with target.open("x", encoding="utf-8") as output:
    output.write(content)
try:
    target.chmod(0o600)
except PermissionError:
    pass
print(".env er oprettet til lokal test. Ingen standardbruger eller adgangskode er oprettet.")
print("Brug http://127.0.0.1:8000. Se README.md før netværks-/produktionsdrift.")
