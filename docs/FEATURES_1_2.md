# ProxPortal 1.2.0 – nye funktioner

- **Om-knap** på forside og i navigation: brugsvejledning og forslag til lokale regler (ikke juridisk bindende UCN-politik uden godkendelse).
- **Ekstra studerende** ved oprettelse af ansøgning, maks. 15. Feltet benytter `Navn; e-mail; klasse` på hver linje. Valideres, normaliseres og gemmes atomisk i `case_participants`; eksisterende sager får en tom liste.
- **Forlængelsesanmodning** fra hovedansøgeren via privat statussession; kun godkendte/aktive sager. Administrator godkender/afviser og skriver meddelelse. Status, beslutning og slutdato gemmes transaktionssikkert. Oprindeligt ønsket slutdato forbliver uændret.
- **Sikkerhed**: Andre gruppemedlemmer får ikke automatisk rettigheder eller egen statuskode. Del ikke statuskode med gruppen. Administratoren skal kontrollere identitet før tildeling. Brug af brugerdata kræver institutionens privatlivsvurdering.
- **Migration**: `002_participants_lease.sql`. Eksisterende `cases`, sagsnumre, admin-konti og data bevares.
- **Deployment**: `git pull --ff-only origin main` og `docker compose up -d --build --force-recreate web`. Tag SQLite-backup først.
