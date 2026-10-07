# Ændringslog

## 1.2.0 — 7. oktober 2026

- Tilføjet tydelig »Om og regler«-knap på forsiden og i navigationen med brugervejledning og forslag til lokale laboratorieregler.
- Op til 15 ekstra studerende pr. ansøgning med navn, e-mail og klasse, med servervalidering og ny database-relation.
- Ansøgeren kan anmode om forlængelse af lease med ny ønsket dato og begrundelse.
- Administratoren kan godkende eller afvise anmodningen, og alle beslutninger registreres i historikken.
- Ventende forlængelser markeres på administratoroversigten og blokerer modstridende direkte forlængelse/afslutning.
- Migration 002 bevarer gamle sagsnumre, konti og historik. Funktionstests er kørt lokalt; produktionsopdatering kræver lokal accepttest.


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
