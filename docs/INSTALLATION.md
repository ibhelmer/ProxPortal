# Installation og drift af ProxPortal

Version 1.1.0 · 7. oktober 2026 · Copyright © 2026 Ib Helmer Nielsen

## 1. Placering i Proxmox-miljøet

Placér portalen på en separat Debian- eller Ubuntu-VM. Installer ikke programmet direkte på Proxmox-hypervisoren. Programmet behøver hverken root-login, API-token eller netværksadgang til Proxmox for at behandle ansøgninger.

Et **startforslag**, ikke et målt kapacitetskrav, er 2 vCPU, 2 GiB RAM og 20 GiB systemdisk med plads til opdateringer og lokale arbejdsfiler. Database og backupbehov afhænger af antal sager og institutionens opbevaringstid. Programmet har ikke filvedhæftninger.

Brug én portalinstans med databasen på lokal disk. En almindelig virtuel disk i VM’en er velegnet; SQLite-filen må ikke deles mellem flere portal-VM’er på et netværksfilsystem. SQLite har kun én samtidig skriver, hvilket er grunden til den valgte single-instance-afgrænsning. Se SQLite-referencen i README.

## 2. Udvælg installation

Der følger to veje med: lokal Python-kørsel og en Docker Compose-opsætning. Python 3.13 er afprøvet. Containeren er beskrevet med `python:3.13-slim`; selve Docker-buildet er ikke kørt i leverancens testmiljø.

Docker Engine og Compose skal være installeret på forhånd. Følg Docker-projektets egne distributionsspecifikke instruktioner frem for at kopiere ældre install-scripts:

- Debian: <https://docs.docker.com/engine/install/debian/>
- Ubuntu: <https://docs.docker.com/engine/install/ubuntu/>

## 3. Lokal Python-afprøvning

Klon repoet med `git clone https://github.com/ibhelmer/ProxPortal.git`, og åbn en terminal i mappen `ProxPortal`. Alternativt udpakkes projektarkivet.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python scripts/setup_env.py
python manage.py init-db
python manage.py create-admin --email admin@example.org --name "Din administrators navn"
python -m uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Er `python3 -m venv` ikke tilgængelig, skal distributionens pakke til Python-venv installeres først. Vælg egen e-mail og navn ved oprettelsen af administratoren. Adgangskoden indtastes skjult og har ingen standardværdi.

På samme computer åbnes:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/admin/login
```

Køres programmet på en fjern-VM, anvendes en SSH-tunnel på din arbejdscomputer:

```bash
ssh -L 8000:127.0.0.1:8000 dit-login@DIN-VM-IP
```

Åbn fortsat `http://127.0.0.1:8000` lokalt. Programmet er i testtilstand og viser en gul testmarkering. Brug kun fiktive oplysninger på dette tidspunkt.

## 4. Docker Compose

Fra projektmappen:

```bash
python3 scripts/setup_env.py
docker compose up -d --build
docker compose exec web python manage.py create-admin \
  --email admin@example.org --name "Din administrators navn"
docker compose ps
docker compose logs --tail 100 web
```

Databasen oprettes ved opstart. Nye databasemigrationer køres, men eksisterende sager slettes ikke.

Compose anvender en navngiven volumen til `/data`. Kodefilsystemet er skrivebeskyttet, og programmet kører som UID/GID 10001. Kun `/data` og et midlertidigt `/tmp` er skrivbare. Port 8000 er kun publiceret på værtsmaskinens loopbackadresse.

```text
Browser → HTTPS/reverse proxy → 127.0.0.1:8000 → webcontainer → /data/labportalen.sqlite3
```

**Kør ikke `docker compose down -v`, når sager skal bevares.** Flaget `-v` kan fjerne den vedvarende databasevolumen. Normal genstart/opdatering skal bevare volumenet og samme Compose-projektnavn.

## 5. Institutionens opsætning

Redigér `.env`. Eksempelværdierne nedenfor skal erstattes med jeres faktiske adresser:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://vmportal.example.org
ALLOWED_HOSTS=vmportal.example.org,127.0.0.1
SECURE_COOKIES=1
ORGANIZATION=UCN
PORTAL_NAME=ProxPortal
SUPPORT_EMAIL=it-support@example.org
PRIVACY_URL=https://www.example.org/privatliv
ALLOWED_EMAIL_DOMAINS=ucn.dk,stud.ucn.dk
```

E-maildomænerne er **eksempler**, ikke en verificeret liste over jeres aktuelle institutionsdomæner. Indsæt de faktiske domæner. Lad feltet være tomt, når domænebegrænsning ikke ønskes. Restriktionen er ikke en e-mail- eller identitetsverifikation.

`PUBLIC_BASE_URL` skal være portalens præcise adresse uden understi. `ALLOWED_HOSTS` er værtsnavne uden protokol, port eller sti. `127.0.0.1` beholdes til containerens sundhedskontrol. Adressen i browseren og Origin-headeren skal matche `PUBLIC_BASE_URL`.

Er `APP_ENV=production`, nægter programmet at starte uden både en HTTPS-adresse og `SECURE_COOKIES=1`. Dette etablerer ikke i sig selv TLS; reverse proxy og certifikat skal stadig opsættes.

Ressourcegrænser kan tilpasses:

```dotenv
MAX_VCPU=64
MAX_RAM_GIB=512
MAX_STORAGE_GIB=8192
MAX_DURATION_DAYS=730
```

Tallene er formulargrænser, ikke kendskab til clusterets faktiske kapacitet. Administratoren skal selv vurdere kapacitet og rettigheder. En ny periode må højst omfatte `MAX_DURATION_DAYS` inklusive begge datoer; en forlængelse kan gå højst dette antal dage frem fra godkendelsesdagen.

## 6. Nginx og HTTPS

Eksempelkonfiguration findes i `deploy/nginx.conf.example`. Den forudsætter Nginx på VM’en foran loopback-porten. Tilpas DNS-navn samt certifikat- og nøglestier. Anvend et certifikat, jeres brugeres browsere stoler på.

Kontrollér opsætningen med `nginx -t`, inden Nginx genindlæses. Åbn kun de nødvendige netværksporte og begræns administrationen til det relevante interne net/VPN. Portalen har ikke MFA eller institutions-SSO i denne version.

Uvicorn startes med `--no-proxy-headers`, og programmet accepterer kun `X-Real-IP` fra præcist oplyste proxy-IP’er. Dette forhindrer, at vilkårlige klienter selv vælger deres rate-limit-identitet via proxyheadere.

Ved Nginx og **native Python på samme VM**:

```dotenv
TRUSTED_PROXY_IPS=127.0.0.1
```

Ved Nginx på værts-VM’en og app i Docker vil forbindelsen typisk ses fra Docker-netværkets gateway. Kontroller den faktiske gateway:

```bash
docker inspect "$(docker compose ps -q web)" \
  --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
```

Indsæt den faktiske IP i `TRUSTED_PROXY_IPS`, og genopret appcontaineren. Kopiér ikke en tilfældig `172.x.x.x`-adresse fra andre miljøer. Ved en anden proxyarkitektur skal den faktiske nærmeste proxy identificeres særskilt. `X-Real-IP` skal overskrives af proxyen, ikke blot videresendes fra klienten.

```bash
docker compose up -d --force-recreate
```

Uden korrekt proxy-IP deles IP-baserede rate limits af alle brugere bag proxyen. Standardgrænsen er 120 indsendelser/time/IP og 5/time/e-mail. Administratorlogin er begrænset til 10 forsøg/15 minutter/IP og 20/15 minutter/e-mail. Statusopslag er begrænset til 60/15 minutter/IP. Serverens tabel deler tællerne mellem processer; de ligger ikke alene i hukommelsen.

## 7. Systemd uden Docker

Et eksempel findes i `deploy/labportalen.service.example`. Opret en dedikeret Linux-bruger og installér projekt og virtuelt miljø under `/opt/labportalen`. Tilpas stier, ejerskab og `.env`, så brugeren kan læse koden og kun skrive databasekataloget.

Eksemplet forudsætter:

```text
Bruger:          labportalen
Projekt:         /opt/labportalen
Python:          /opt/labportalen/.venv/bin/python
Database:        /opt/labportalen/data/labportalen.sqlite3
Indstillinger:   /opt/labportalen/.env
```

Kør `manage.py create-admin` som programbrugeren med samme virtuelle miljø og `.env`, før systemet overdrages. Nginx/TLS fungerer efter samme princip som Docker-opsætningen.

## 8. Backup

Brug backupkommandoen. Den benytter SQLite-backup-API’en, så der oprettes en sammenhængende kopi, også når databasen er åben. En løs kopiering af kun `.sqlite3` fra et aktivt WAL-miljø kan udelade data.

Lokal installation:

```bash
python manage.py backup --output backups/labportalen-2026-10-06.sqlite3
```

Docker:

```bash
docker compose exec web python manage.py backup \
  --output /data/backups/labportalen-2026-10-06.sqlite3
mkdir -p backups
docker compose cp web:/data/backups/labportalen-2026-10-06.sqlite3 ./backups/
chmod 600 backups/labportalen-2026-10-06.sqlite3
```

Vælg et nyt filnavn for hver backup. Kommandoen overskriver ikke en eksisterende backup og udfører `PRAGMA integrity_check`. Websessioner og midlertidige rate-limit-tællere er fjernet fra backupkopien; sager, administratorer og historik er bevaret.

Flyt sikkerhedskopien til et godkendt separat backupsted. En fil i samme VM/volumen er ikke tilstrækkelig beskyttelse ved tab af VM’en eller storage. `.env` og øvrig konfiguration skal sikkerhedskopieres særskilt og beskyttes som hemmeligheder.

### Gendannelse

Afprøv først gendannelse i et isoleret testmiljø. Stop alle portalprocesser, og tag en frisk backup af den nuværende database, før en gendannelse foretages. Det er et bevidst overskrivningstrin.

**Native installation:** Stop systemd-servicen. Erstat databasefilen med den valgte, verificerede backup. Fjern kun eventuelle gamle `-wal`/`-shm`-sidefiler, når alle databasebrugere er stoppet og den gamle database er sikret. Bevar ejer og filrettigheder (0600 til programbrugeren). Kør `manage.py init-db` med den tilhørende programversion, og start servicen.

**Docker:** Stop `web`. Den følgende engangskommando bruger det samme datavolumen og monterer dit lokale backupkatalog skrivebeskyttet. Erstat filnavnet med den ønskede backup. Der må ikke køre andre containere/processer mod samme SQLite-fil:

```bash
docker compose stop web

docker compose run --rm --no-deps \
  -v "$PWD/backups:/restore:ro" web python -c '
from pathlib import Path
import sqlite3, shutil, os
source = Path("/restore/labportalen-2026-10-06.sqlite3")
target = Path("/data/labportalen.sqlite3")
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as c:
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] > 0
staged = target.with_suffix(".restore-tmp")
shutil.copyfile(source, staged)
staged.chmod(0o600)
for suffix in ("-wal", "-shm"):
    Path(str(target) + suffix).unlink(missing_ok=True)
os.replace(staged, target)
print("Database erstattet. Start og kontrollér applikationen.")
'

docker compose up -d web
docker compose logs --tail 100 web
```

Backupfilen i det monterede katalog skal kunne læses af containerens UID 10001. Tildel målrettet læseadgang eller passende ejerskab på en separat gendannelseskopi; gør ikke hele backupområdet offentligt læsbart. Kommandoen ovenfor er en driftsopskrift og er ikke kørt med Docker i leverancens testmiljø.

Kontrollér efterfølgende: adminlogin, antal sager, en nyere sag, historik, sagsnummersekvens og private statusopslag. Eksisterende websessioner skal ikke kunne genbruges fra backup.

## 9. Vedligeholdelse

Tag backup før ændringer. Bevar `.env` og datavolumen. Anvend nye afhængighedsversioner efter gennemgang og regressionstest; de medfølgende versionsfiler er et fast testgrundlag, ikke en løbende opdateringstjeneste.

Docker-opdatering af kode/image:

```bash
docker compose exec web python manage.py backup --output /data/backups/foer-opdatering.sqlite3
docker compose build --pull
docker compose up -d
docker compose logs --tail 100 web
```

Brug et nyt backupfilnavn ved næste opdatering. En nyere database må ikke åbnes med en ældre programudgave; dette kontrolleres ved opstart.

`python manage.py maintenance` fjerner udløbne sessioner og rate-limit-tællere, ikke sager eller Proxmox-ressourcer. `python manage.py list-expiring --days 14` kan indgå i en lokal driftsrutine. Portalen har ingen indbygget scheduler eller e-mailservice.

## 10. Accepttest inden brug med rigtige ansøgninger

Afprøv en studerende med VM, en underviser med adgang, afvisning med begrundelse, godkendelse, manuel levering, forlængelse, afvikling, arkivering og gendannelse fra arkiv. Kontroller fra en separat browser, at status kræver privat kode, og at interne notater ikke vises.

Kontrollér HTTPS, sessionscookies, værtsnavn/Origin, proxy-IP’er, rate limits bag fælles NAT, personlig adminadgang, driftsovervågning og gendannelse af backup. Institutionen skal have færdiggjort kontakt- og privatlivsinformation samt opbevarings-/sletteproces. Arkivering sletter ikke personoplysninger, og denne version har ikke automatisk sletning.

Der er ikke foretaget en uafhængig penetrationstest, belastningstest i jeres miljø eller en juridisk vurdering af institutionens konkrete brug.
