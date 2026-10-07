# Ændringslog

## 1.1.1 — 7. oktober 2026

- Rettet browserlogin og øvrige HTML-formularer, hvor `Referrer-Policy: no-referrer` fik Chromium til at sende `Origin: null` og udløste HTTP 403.
- Svarheaderen ændret til `Referrer-Policy: same-origin`, så same-origin POST sender korrekt Origin uden referrer-oplysninger til andre domæner.
- CSRF-token og afvisning af `Origin: null`/fremmede origins er bevaret og regressionstestet.
- Eksisterende data og administratorkonti ændres ikke ved opgradering.


## 1.1.0 — 7. oktober 2026

- Publicering som ProxPortal med samme ansøgnings- og sagsbehandlingsfunktioner.
- UCN-logo som lokal SVG, bevaret fra den eksisterende UCN-designskabelon.
- UCN-palettokens og tilpasset header, knapper, kort og mobilvisning.
- Den leverede favicon indsat med tabsfri PNG-komprimering i ICO-format; samme pixels ved alle tre originale størrelser. Tilgængelig via `/favicon.ico`.
- Ikonkald opretter ikke sessioner; tilføjet versionsstyret ikonhenvisning og temafarve.
- Rettet vandret dokumentoverløb omkring administratorens tabel ved smalle skærme.
- 14 nye brandingtests; i alt 83 beståede tests.
- Databaseformat, sagsnumre, filnavne og Docker-volumen bevaret for kompatibilitet.

## 1.0.0 — 6. oktober 2026

Første LabPortalen-leverance med ansøgninger, private statuskoder, administratorgodkendelse, manuel leveringsregistrering, udløbsopfølgning, arkivering, CSV-eksport og backup. Ingen automatiske ændringer i Proxmox.
