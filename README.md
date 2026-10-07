# ProxPortal 1.1.0

**Webbaseret ansøgning, godkendelse og arkivering af virtuelle undervisningsmiljøer.**

Copyright © 2026 Ib Helmer Nielsen. Apache License 2.0.

Studerende og undervisere kan ansøge om en virtuel maskine eller adgang til et Proxmox-cluster. Administratorer kan behandle sager, registrere levering, følge op på udløb og arkivere afsluttede eller afviste ansøgninger.

Brugerfladen og denne dokumentation er på dansk. Kode, funktionsnavne og kodekommentarer er på engelsk.

## Hvad følger med?

| Område | Implementeret |
|---|---|
| Ansøger | Studerende/underviser, navn, klasse for studerende og e-mail |
| Behov | Ansøgningstype, titel og beskrivelse af formålet |
| VM | OS-familie, version/udgave, vCPU, RAM i GiB og storage i GiB |
| Adgang | Beskrivelse af ønskede miljøer, ressourcer og rettigheder |
| Periode | Ønsket start og slut, inklusive slutdagen; automatisk beregning af antal dage |
| Registrering | Database og unikt sagsnummer, eksempelvis `LAB-2026-000001` |
| Ansøgerstatus | Privat statusside med sagsnummer + hemmelig kode |
| Administration | Login, søgning, filtre, sideinddeling, godkendelse og afvisning |
| Levering | Manuel registrering af node + VMID eller tildelt Proxmox-konto |
| Dokumentation | Historik med sagsbehandler og tidspunkt; offentlige beskeder og særskilte interne notater |
| Udløb | Markering af udløbne tildelinger og dem, der udløber inden 14 dage |
| Forlængelse | Ny tildelingsslutdato og begrundelse; oprindelig ønsket periode bevares |
| Arkiv | Afviste/afsluttede sager bevares og kan hentes fra arkivet |
| Eksport/drift | Filtreret CSV, backupkommando, versionerede databasemigrationer og Docker Compose |

**Afgrænsning:** Der foretages ingen kald til Proxmox i denne version. Der oprettes, ændres eller slettes ikke VM’er, brugere eller rettigheder. Ingen automatisk e-mail, Entra ID/AD/LDAP-login, MFA, e-mailverifikation eller automatisk persondatasletning er implementeret. E-mailfeltet er kontaktinformation, ikke bevis for identitet.

## Hurtig lokal afprøvning

Hent projektet, og kør fra repoets rodmappe:

```bash
git clone https://github.com/ibhelmer/ProxPortal.git
cd ProxPortal
```

 Python 3.13 er den afprøvede Python-version. Brug først fiktive oplysninger.

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python scripts/setup_env.py
python manage.py init-db
python manage.py create-admin --email admin@example.org --name "Din administrators navn"
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Vælg din egen administratoradresse og dit eget navn. Kommandoen spørger efter en adgangskode på 14–128 tegn; den indtastes skjult. **Der findes ingen standardkonto eller standardadgangskode.**

Åbn `http://127.0.0.1:8000`. Administratorlogin er `http://127.0.0.1:8000/admin/login`.

`PUBLIC_BASE_URL` skal stemme med den adresse, der bruges i browseren. Standardopsætningen bruger præcist `http://127.0.0.1:8000`, ikke en vilkårlig LAN-adresse.

### Windows / PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe scripts\setup_env.py
.\.venv\Scripts\python.exe manage.py init-db
.\.venv\Scripts\python.exe manage.py create-admin --email admin@example.org --name "Din administrators navn"
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Der er ikke behov for at ændre PowerShells scriptpolitik, da kommandoerne anvender miljøets Python direkte. Windows-forløbet er ikke kørt i det leverede testmiljø.

## Docker på en separat Linux-VM

Forudsætter en fungerende installation af Docker Engine og Docker Compose. Se [installationsvejledningen](docs/INSTALLATION.md) for drift bag HTTPS, lokale porte og backup.

```bash
python3 scripts/setup_env.py
docker compose up -d --build
docker compose exec web python manage.py create-admin --email admin@example.org --name "Din administrators navn"
docker compose ps
```

Den vedvarende database ligger i Docker-volumenet `labportalen_labportalen-data`. Den konkrete volumenbetegnelse kan kontrolleres med `docker volume ls`; ændret Compose-projektnavn ændrer også volumenets navn.

Port 8000 publiceres **kun på VM’ens loopbackadresse**. Test fra VM’en eller brug en SSH-tunnel fra din egen computer:

```bash
ssh -L 8000:127.0.0.1:8000 dit-login@DIN-VM-IP
```

Åbn derefter `http://127.0.0.1:8000` på din computer. En reverse proxy med HTTPS skal sættes op, før portalen åbnes for almindelige brugere. Pakken installerer ikke Docker og udsteder ikke TLS-certifikater automatisk.

## Ansøgningsforløbet

1. Ansøgeren udfylder formularen og får en kvittering med sagsnummer og privat kode.
2. Administratoren kontrollerer identitet, klasse/tilknytning, formål og kapacitet. Valget ”underviser” giver aldrig administratoradgang.
3. Ansøgningen godkendes eller afvises. Ansøgeren ser beskeder på sin statusside; der sendes ingen automatisk e-mail.
4. En godkendt VM/adgang oprettes manuelt i Proxmox. Administratoren vælger derefter ”Registrér VM / adgang som leveret”.
5. Ved udløb afvikles ressourcen manuelt eller perioden forlænges. Sagen afsluttes og kan derefter arkiveres.

En ansøgning om VM og en ansøgning om clusteradgang er to separate sager i denne version. En VM-ansøgning beskriver én VM; der oprettes ikke en hel gruppe af VM’er fra én formular.

### Status og arkiv

```text
Modtaget → Under behandling → Godkendt → Leveret / aktiv → Afsluttet
    └──────────────────────→ Afvist

Afvist / Afsluttet → Arkiveret
Arkiveret → Hent fra arkiv (bevarer tidligere status)
Afvist → Under behandling (ny vurdering)
```

Godkendelse og afvisning kan også ske direkte fra ”Modtaget”. En uleveret ansøgning kan afsluttes med en begrundelse. Ved afslutning af en godkendt eller aktiv tildeling skal administratoren bekræfte, at miljøet er afviklet eller aldrig blev oprettet.

**Udløb er en opfølgningsmarkering, ikke en automatisk sletning.** En aktiv VM, der er udløbet, bliver stadig vist som aktiv med advarsel, indtil administratoren registrerer afslutning. Der må ikke arkiveres aktive/godkendte tildelinger, så de forsvinder fra opfølgningen.

## Teknologi og database

Python/FastAPI med Uvicorn, Jinja2, lokal HTML/CSS/JavaScript og SQLite. Version 1 er beregnet til **én portalinstans på én VM med lokal disk**. Der er ikke implementeret en PostgreSQL-backend eller aktiv/aktiv-drift på tværs af noder.

Databasen bruger parameteriserede SQL-forespørgsler, fremmednøgler, WAL og korte transaktioner. Sagsnummer og første historikhændelse skrives i samme transaktion. Nummereringen begynder ved 1 i et nyt år, og både sagsnummer og indsendelsesnøgle har en database-unikhedskontrol.

En gentagen indsendelse af samme formular giver samme sag og kvittering. Åbnes og indsendes en ny formular, er det en ny ansøgning. Sagsbehandlingen anvender versionskontrol, så to administratorer ikke ubemærket overskriver hinandens ændringer.

Databasefilerne indeholder personoplysninger i læsbar form. Der er **ikke indbygget databasekryptering**. OS-adgang, disk-/backupkryptering, opbevaringsregler og sikkerhedskopiering er institutionens driftsansvar.

## Administratorværktøjer

```bash
python manage.py list-admins
python manage.py reset-password --email admin@example.org
python manage.py disable-admin --email anden-admin@example.org
python manage.py enable-admin --email anden-admin@example.org
python manage.py list-expiring --days 14
python manage.py maintenance
python manage.py backup --output backups/labportalen-backup.sqlite3
```

I Docker sættes `docker compose exec web` foran `python manage.py ...`. Backup skal i Docker skrives under `/data`, f.eks. `/data/backups/labportalen-backup.sqlite3`.

En mistet privat statuskode kan fornyes fra serveren efter manuel identitetskontrol:

```bash
python manage.py rotate-status-code \
  --case-number LAB-2026-000001 \
  --admin-email admin@example.org \
  --confirm-identity
```

Kommandoen udskriver en ny kode, tilbagekalder tidligere statussessioner og registrerer handlingen i historikken. En arkiveret sag skal først hentes fra arkivet. Koden skal udleveres via en passende, verificeret kontaktkanal.

## Opsætning og sikkerhed

`python scripts/setup_env.py` opretter en `.env` med en tilfældig 256-bit hemmelighed. Scriptet overskriver aldrig en eksisterende fil. `.env` og databasefiler må ikke lægges i Git.

Administratoradgangskoder hashes med Argon2id (64 MiB, tre iterationer, parallelisme 1). Sessioner ligger på serveren; browseren har kun en tilfældig nøgle i en HttpOnly/SameSite-cookie. Alle formularændringer kræver en CSRF-token. Der er desuden afgrænsede værtsnavne, Origin-kontrol, størrelsesgrænse for formularer, rate limits og sikkerhedsheadere. Kode og privat statuskode sendes ikke som URL-parametre.

I `.env` kan der indstilles grænser for vCPU, RAM, storage og periode samt e-maildomæner, organisationsnavn, kontaktadresse og institutionens privatlivsinformation. Domænebegrænsning validerer adressens format/domæne; den bekræfter ikke, at ansøgeren ejer adressen.

Historikhændelser kan ikke redigeres eller slettes via portalen. Databasetriggere stopper almindelige SQL-opdateringer/sletninger af historik. Dette er **ikke** en manipulationssikker ekstern revisionslog mod en server- eller databaseadministrator.

## Test og skærmbilleder

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Se [testrapporten](docs/TESTREPORT.md) for de faktisk kørte kontroller og afgrænsninger. Docker-installation, produktions-TLS og integration med institutionens miljø skal accepttestes lokalt.

Skærmbillederne anvender udelukkende fiktive demonstrationseksempler. Der følger **ingen demodatabase, aktiv demo-login eller `.env`** med udgivelsen.



## UCN-design og favicon

Brugerfladen er tilpasset UCN med originalt logo, UCN 2022-temaets farver og projektets vedhæftede favicon. Logo og ikon serveres lokalt uden eksterne kald. Se [branding og kildeangivelse](docs/BRANDING.md).

Den synlige portal hedder nu **ProxPortal**. Databaseskema, `LAB-ÅÅÅÅ-NNNNNN`-sagsnumre, cookie-navn, databasefil og Docker-volumen beholder deres hidtidige tekniske navne af hensyn til eksisterende installationer. Der oprettes ikke en tom erstatningsdatabase ved blot at skifte navn i brugerfladen. Sæt `PORTAL_NAME=ProxPortal` i en eksisterende `.env` for at opdatere navnet.

## Dokumentation

- [Installation, drift og backup](docs/INSTALLATION.md)
- [Datamodel og sagsregler](docs/ARCHITECTURE.md)
- [Testresultater og afgrænsninger](docs/TESTREPORT.md)
- [Sikkerheds- og driftsnoter](SECURITY.md)
- [Licens](LICENSE)

## Primære tekniske referencer

Implementeringen og driftsanvisningerne er udarbejdet med udgangspunkt i FastAPIs deployment-dokumentation, Python/SQLite, Starlette og OWASP. Kilderne er kontrolleret 6. oktober 2026; afhængighedsfilerne er et afprøvet versionssæt og er ikke en påstand om at være de nyeste eller fri for alle kendte sårbarheder.

- [FastAPI: containers og deployment](https://fastapi.tiangolo.com/deployment/docker/)
- [Python: sqlite3, transaktioner og backup](https://docs.python.org/3/library/sqlite3.html)
- [SQLite: passende anvendelser og begrænsninger](https://sqlite.org/whentouse.html)
- [Starlette: middleware og TrustedHostMiddleware](https://starlette.dev/middleware/)
- [OWASP: Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
