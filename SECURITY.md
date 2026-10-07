# Sikkerheds- og driftsnoter

ProxPortal er en første applikationsversion til kontrolleret institutionsdrift. Der er ikke udført uafhængig penetrationstest eller juridisk vurdering. De automatiske tests verificerer konkrete funktioner, ikke fravær af alle sikkerhedsfejl.

## Implementerede foranstaltninger

- Personlige administratorkonti; ingen standardkonto, ingen selvregistrering og ingen administratorrolle fra ansøgningsformularen.
- Argon2id-passwordhashing, serverbaserede sessioner, udløb og sessionsrotation ved login/statusadgang.
- CSRF-token på formularer, Origin-/Host-kontrol, HttpOnly/SameSite-cookie og Secure-cookie i produktion.
- Parameteriseret SQL, servervalidering, HTML-escaping, lokal frontend og en restriktiv Content Security Policy.
- Databasebaserede rate limits, formularstørrelsesgrænse, ingen filuploads og ingen uvedkommende Proxmox-rettigheder.
- Transaktioner, unikke sagsnumre, idempotent indsendelse og versionskontrol ved sagsændring.
- Hash af private statuskoder; statuskode sendes ikke i URL eller CSV. Interne notater vises ikke til ansøgeren.
- Opdeling mellem godkendelse, manuel levering og afvikling; aktive ressourcer kan ikke skjules ved direkte arkivering.

## Forudsætninger før rigtig drift

Brug HTTPS og en korrekt opsat reverse proxy. Hold app- og databaseporte interne. Begræns portalens netværkseksponering; især administratoradgangen bør beskyttes med institutionens net/VPN eller godkendte identitetsløsning. Indbygget MFA, OIDC, LDAP, e-mailverifikation og CAPTCHA er ikke en del af version 1.

Kontrollér ansøgerens identitet og tilknytning manuelt. Institutionen skal fastlægge adgangsregler, privatlivsinformation, opbevarings-/slettefrister samt en proces for rettelse og andre datahenvendelser. Arkivering bevarer oplysningerne. Der er ingen automatiseret persondatasletning.

Database og backup er ikke krypteret af programmet. Beskyt filrettigheder, disk, backupsted og administratorarbejdsstationer. En administrator på serveren kan læse/ændre hele databasen; historikken er ikke en ekstern manipulationssikker revisionslog.

En hemmelig statuskode giver adgang til én sag og skal behandles som en adgangskode. Del den ikke i undervisningsslides, offentlige kanaler eller supportsager, som uvedkommende kan se. Ved tab/fejludlevering kan serverens kodefornyelseskommando tilbagekalde koden og tidligere statussessioner efter identitetskontrol.

Gennemgå logopbevaring. Appen starter uden Uvicorn-accesslog. Nginx-eksemplet undlader query-strenge og request bodies, men registrerer klient-IP. Produktionslogning kan afhænge af andre komponenter; institutionens regler skal også dække disse.

Fasthold et vedligeholdt og testet versionssæt. De leverede pins er hentet fra det anvendte testmiljø og er ikke en garanti for at være de nyeste, en SBOM-certificering eller en sårbarhedsgodkendelse. Opdater afhængigheder kontrolleret og gentag test og lokal accepttest.

## Kendte funktionsgrænser

Ingen institutionel SSO/MFA, automatisk e-mail eller indbygget mailkø. Ingen HA/aktiv-aktiv-drift og ingen PostgreSQL-backend. Ingen Proxmox-API, automatiseret kapacitetskontrol, netværksisolering af bestilte VM’er, livscyklussletning eller faktisk kontrol af, om administratorens leverings-/afviklingsregistrering svarer til clusterets tilstand.

Alle portaladministratorer kan behandle alle sager. Der er ikke finmaskede rettigheder pr. klasse/afdeling. Administration fra CLI kræver lokal kontrol med serveren og er ikke beskyttet af web-login.

Sagsnumre kan forudsiges og er ikke adgangslegitimation. En private kode eller administratoradgang kræves for sagsopslag. Statusadgang bør erstattes/suppleres med institutionel identitet, hvis jeres dataklassifikation kræver det.
