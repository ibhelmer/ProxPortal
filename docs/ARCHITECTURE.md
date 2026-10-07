# Datamodel og sagsregler

## Komponenter

`app/main.py` indeholder applikationsfabrik, HTML-ruter og HTTP-beskyttelse. `app/validation.py` validerer formularer på serveren. `app/services.py` indeholder sagsflow, søgning og eksport. `app/security.py` håndterer adgangskoder, sessioner, CSRF-relaterede hjælpefunktioner og rate limits. `app/db.py` håndterer SQLite-forbindelser, transaktioner, migrationer og backup.

`app/templates/` er Jinja2-skabeloner med automatisk HTML-escaping. `app/static/` indeholder lokal CSS og JavaScript. Der er ingen ekstern JavaScript-, font- eller CDN-afhængighed. `manage.py` er værktøjet til lokale administrative operationer.

## Tabeller

| Tabel | Formål |
|---|---|
| `cases` | Ansøgning, tildelingsperiode, status, leveringsoplysninger, versionsnummer og arkivmarkering |
| `case_sequences` | Årsopdelt løbenummer til sagsnumre |
| `case_events` | Hændelser med før/efter-status, sagsbehandler, offentlig besked, internt notat og detaljer |
| `admins` | Personlige administratorkonti med Argon2id-hash og aktivmarkering |
| `web_sessions` | Hash af sessionsnøgle, CSRF-token, admin-/statusadgang og udløbstid |
| `rate_limits` | HMAC-baserede identitetsnøgler og tidsvinduer til begrænsning af forsøg |
| `admin_events` | Login-, eksport- og lokale administrationshændelser |
| `schema_migrations` | Anvendte databasemigrationer |

Relationer: en sag har mange hændelser; en administrator kan være aktør i mange hændelser. En websession kan have en administrator og/eller adgang til én konkret sag. `schema_migrations` og `case_sequences` er systemtabeller.

## Identitet og autorisation

Studerende og undervisere udfylder samme offentligt tilgængelige formular, forudsat netværksadgang til portalen. Der er ingen selvregistrering af administratorer. Angivne rolle, navn, klasse og e-mail skal kontrolleres via en kendt kanal, inden administratoren godkender.

En statuskode er en adgangslegitimation til én sag, ikke bevis for ejerens identitet. Sagsnummeret er ikke hemmeligt og bruges aldrig alene til adgangskontrol. En eventuel kommende Entra ID-/OIDC-integration skal forbindes med verificeret identitet og serverbestemte roller, ikke blot e-maildomæne.

I version 1 kan alle aktive portaladministratorer se alle sager. Der er ikke roller pr. afdeling, pool eller klasse. Alle administratorer skal derfor være autoriserede til det samlede sagsmateriale.

## Registrering og samtidighed

En skjult indsendelsestoken indeholder en kryptografisk tilfældig nonce bundet til den aktuelle session og signeret med en tidsbegrænset signatur. Databasen har en unik `submission_key`. Samme gyldige formular sendt igen returnerer den allerede oprettede sag.

Det læsbare sagsnummer anvender år plus seks cifre, f.eks. `LAB-2026-000001`. Bredden er et minimum; systemet genbruger ikke numre, når en sekvens når mere end seks cifre. Årstal baseres på dansk lokal dato. Sekvens, sag og første hændelse skrives under samme `BEGIN IMMEDIATE`-transaktion.

Administratorformularen medsender sagens versionsnummer. Ved konflikt afvises handlingen med HTTP 409, og administratoren skal genindlæse sagen. Opdatering og historikhændelse gemmes atomisk. Fejl ruller begge dele tilbage.

## Tilstandsregler

| Handling | Tilladte udgangspunkter | Resultat / ekstra kontrol |
|---|---|---|
| Under behandling | Modtaget, afvist | Under behandling |
| Godkend | Modtaget, under behandling | Godkendt; identitetskontrol skal bekræftes; slutdato må ikke være overskredet |
| Afvis | Modtaget, under behandling | Afvist; offentlig begrundelse påkrævet |
| Registrér levering | Godkendt | Aktiv; node+VMID eller Proxmox-konto påkrævet; periode må ikke være udløbet |
| Afslut | Modtaget, under behandling, godkendt, aktiv | Afsluttet; offentlig begrundelse; ved godkendt/aktiv skal afvikling bekræftes |
| Forlæng | Godkendt, aktiv | Gældende slutdato flyttes frem; offentlig begrundelse; oprindelig ønsket slutdato bevares |
| Arkivér | Afvist, afsluttet | Arkivmarkering; intern begrundelse |
| Hent fra arkiv | Arkiveret sag | Arkivmarkering fjernes; tidligere status bevares |
| Notat / besked | Ikke arkiveret | Status uændret, men version og historik opdateres |

Der findes ikke en generel ”redigér ansøgning”-funktion. De oprindelige indsendte oplysninger bevares; afklaringer dokumenteres som beskeder/notater. En forkert ansøgning kan afsluttes og erstattes af en ny sag. En ny ønsket periode, der allerede er udløbet før godkendelse, skal afklares via en ny ansøgning; forlængelsesfunktionen gælder godkendte og aktive tildelinger.

Et afvist forløb kan genoptages via ”Under behandling”. En afsluttet sag genåbnes ikke som aktiv; en ny tildeling registreres i en ny sag. Den leverede VM’s ID og node er dokumentation, ikke en autoritativ synkronisering med Proxmox.

## Tid og udløb

Tidsstempler gemmes i UTC med tidszoneoffset. Visningen omregner til `Europe/Copenhagen`. Start- og slutdato er kalenderdatoer. Den valgte slutdato er inklusive; en sag er først udløbet, når dansk dagsdato er større end slutdatoen.

Periodens længde er `(slutdato - startdato) + 1`. Sommer-/vintertid ændrer derfor ikke antallet af kalenderdage. Det er ikke en garanti for et præcist antal timer.

Udløb vises dynamisk ved opslag. Der er ingen baggrundsproces, der ændrer VM’er, rettigheder eller sagstilstand ved midnat. Oversigten over registrerede VM-ressourcer summerer alle ikke-arkiverede godkendte og aktive VM-sager, inklusive udløbne, fordi de kan være uafviklede. Clusteradgang tæller ikke med som en VM-ressourcetildeling.

## Arkiv, historik og persondata

Arkiv betyder bevarelse med særskilt visning, ikke sletning. Arkiverede sager er skrivebeskyttede i applikationen, indtil de hentes fra arkivet. Arkivmarkeringen er adskilt fra afslutningsstatus.

Historiktabellen er append-only via applikationsregler og databasetriggere. Den er ikke sikret mod en administrator med direkte kontrol over database eller programkode. Institutionens krav til ekstern revision, opbevaring, anonymisering og sletning kræver særskilt design; version 1 har ingen automatisk sletning eller anonymisering.

## Mulig senere Proxmox-integration — ikke implementeret

En efterfølgende integration kan læse godkendte sager, klone institutionens VM-templates og registrere resultatet. Den skal have præcist afgrænsede rettigheder, eksplicit mapping fra OS til template, kapacitets-/netværksvalg og genkørselssikkerhed. ”Godkendt” bør fortsat ikke betyde ”oprettet”, før en faktisk Proxmox-task er bekræftet.

Denne leverance indeholder ikke Proxmox-legitimationsoplysninger, en provisioning-worker eller en slettefunktion. Sagsbehandlingen kan derfor tages i brug uafhængigt af en sådan integration.
