# ProxPortal 1.1.0–1.2.0 — testrapport

Kørt 7. oktober 2026 i det lokale leverancemiljø med Python 3.13.

## Automatiske tests

```bash
python -m pytest -q
```

**83 tests bestået.** Det omfatter de 69 eksisterende tests for ansøgninger, sagsbehandling og sikkerhed samt 14 tests for UCN-branding og favicon.

De eksisterende kontroller omfatter validering af studerende/underviser og VM/adgang, sagsnumre ved samtidige indsendelser, idempotens, autorisation, CSRF, sessioner, rate limits, historik, statussider, godkendelse, levering, afvisning, arkivering, versionskonflikter og databasebackup. Se `tests/test_portal.py` for de konkrete assertions; beståede tests er ikke en fuldstændig sikkerhedsrevision.

De nye kontroller i `tests/test_branding.py` dækker fælles logo/favicon på offentlige sider og fejlsider, lokal SVG uden scripts eller eksterne ressourcer, paletværdier, ikonets kontrolsum og leverede bytes, begge ikonruter, MIME-type, caching, manglende sessionsoprettelse for ikonkald og afvisning af POST til ikonet.

Favicon er tabsfrit komprimeret med PNG-billeder i en ICO-container. En separat programmatisk sammenligning af alle RGBA-pixels ved 16×16, 32×32 og 48×48 pixels bekræftede identisk billedindhold med den vedhæftede original. Filkodningen er ændret; der er ingen skalering eller billedtab. Se originalfilens kontrolsum i `BRANDING.md`.

SHA-256 af den publicerede ICO-fil, som regressionstesten kontrollerer:

```text
29320b9b0a2d17a8daaab7dd02e419574d73c1354b20310b664daf0a82dd6d22
```

## Visuel og JavaScript-kontrol

18 side-/viewport-renderinger blev kontrolleret med Chromium/Playwright: forside, ansøgning, login, administratoroversigt og sagsdetaljer ved relevante skærmbredder mellem 320 og 1440 pixels. Logoet blev indlæst, og ingen side havde vandret dokumentoverløb. Administratorens brede tabel kan fortsat rulles inde i sin egen beholder.

Skift mellem studerende/underviser og VM/clusteradgang blev afprøvet i JavaScript; de relevante felter blev vist, skjult og aktiveret korrekt. Der blev ikke registreret JavaScript-fejl under kontrollen.

**Testmetode:** Miljøets browser blokerede HTTP-navigation. HTML fra den faktiske FastAPI-applikation blev derfor hentet gennem TestClient og renderet i browserens hukommelse med lokale CSS-, JS- og logoressourcer. Dette er visuel/JavaScript-test, ikke en fuld netværksbaseret browser-accepttest. HTTP-responser, sikkerhedsheadere og sessionsadfærd blev testet særskilt med TestClient.

Skærmbillederne fra den tidligere LabPortalen-udgave er ikke publiceret som dokumentation for det nye design. Demonstrationer anvendte alene fiktive personer og `example.org`-adresser. Demodatabase og demoadministrator er ikke med i repoet.

## Ikke afprøvet i denne leverance

Docker-build, produktions-TLS, installation på institutionens VM, institutionslogin, Proxmox-integration, belastningstest og en ekstern sikkerhedsrevision er ikke gennemført. Proxmox-API-integration og institutionslogin er fortsat ikke implementeret.

Kør tests og en reel browser-accepttest efter installation, og afprøv backup/gendannelse på en kopi, før systemet bruges med personoplysninger.


## Udvidelser i version 1.2.0

De nye funktioner er afprøvet i en separat lokal FastAPI/SQLite-testkopi. **78 tests bestod i dette miljø**, dækkende den oprindelige funktionssuite og nye tests for gruppemedlemmer, ugyldige eller gentagne e-mailadresser, ansøgerstatus, forlængelsesbeslutninger, adgangskontrol, versionskonflikt og migration 002. Testkopien indeholdt ikke alle særskilte UCN-brandingtests fra den tidligere GitHub-udgave; de skal køres samlet efter checkout fra `main`.

Bemærk: Docker-build, institutionens HTTPS-miljø og opdatering af en database med eksisterende personoplysninger er ikke blevet testet her. Tag backup og kør en fuld accepttest ved implementering.
