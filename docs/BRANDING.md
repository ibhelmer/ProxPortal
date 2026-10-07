# UCN-design i ProxPortal

Version 1.1.0 · 7. oktober 2026

## Kilde og afgrænsning

Logo og farver er genbrugt fra UCN 2022-temaet i den eksisterende UCN-præsentation `Netvaerksteknologi_Modul05_ITT-CSD-S26_UCN.pptx`. Præsentationen er alene brugt som designkilde og er **ikke** publiceret i dette repository. Dette er ikke en påstand om at have kontrolleret UCN's seneste brandmanual eller fået institutionel godkendelse af portalen.

Logoet kommer fra `ppt/media/image1.emf`. De eksisterende vektorkonturer er konverteret til SVG med Inkscape; symbol, tekst, farve og proportioner er bevaret. SVG-filen bruger kun lokale vektorstier og har ingen scripts, indlejrede skrifttyper eller eksterne ressourcer.

## Farver

Værdier fra `ppt/theme/theme1.xml` i designkilden:

| Farve | HEX | Anvendelse |
|---|---|---|
| Mørk petrol, accent 1 | `#004250` | Logo, primære knapper, overskrifter og mørke paneler |
| Petrol, dark 2 | `#00646E` | Links, fokusmarkering og hover |
| Turkis, accent 2 | `#0096A0` | Dekorative kanter og aktive markeringer |
| Mint, light 2 | `#A5DCCD` | Trinmarkører og lyse kontraster |
| Lys blå, accent 3 | `#BED6DB` | Kanter og sekundære elementer |
| Gul, accent 4 | `#FFE673` | Begrænsede fremhævninger |
| Orange, accent 5 | `#FFC87D` | Supplerende palettoken |
| Koral, accent 6 | `#FFA591` | Supplerende palettoken |

Baggrunds-, tekst- og statusfarver er supplerende UI-farver. Turkis bruges ikke som baggrund for små hvide knaptekster; de primære knapper bruger mørk petrol. Brugerfladen bruger systemskrifttyper, ikke en distribueret UCN-brandfont.

Paletten vedligeholdes som `--ucn-*`-variabler øverst i `app/static/style.css`.

## Favicon

`app/static/favicon.ico` bruger billedindholdet fra den vedhæftede `favicon(1).ico`. De tre originale størrelser, 16×16, 32×32 og 48×48 pixels, er bevaret uden skalering. Filen er kodet med **tabsfri PNG-komprimering inde i ICO-formatet**, så den fylder 2.079 bytes i stedet for 15.406 bytes. Alle RGBA-pixels ved alle tre størrelser er sammenlignet programmatisk og er identiske med originalen. Filens binære kodning er dermed ændret, men ikke billedindholdet.

SHA-256 af originalfilen:

```text
c4abbf8006b75d96be6d1a8b83cf71b3149830ed4634f7ec72b25db9eb88d6c7
```

SHA-256 af den publicerede, tabsfrit komprimerede ICO-fil:

```text
29320b9b0a2d17a8daaab7dd02e419574d73c1354b20310b664daf0a82dd6d22
```

Ikonet tilbydes på både `/favicon.ico` og `/static/favicon.ico`. Alle HTML-sider henviser til `/favicon.ico?v=1.1.0` via den fælles skabelon. Standardikonruten opretter ingen session og kan caches i et døgn. Versionsparameteren opdateres sammen med programversionen.

## Placering og rettigheder

- `app/static/ucn-logo.svg`: UCN-logo. UCN beholder rettighederne til logo og varemærker.
- `app/static/favicon.ico`: projektets leverede ikon. Der gives ikke en ny licens til dette aktiv her.
- `app/templates/base.html`: fælles header, favicon og browserens temafarve.
- `app/static/style.css`: farver og responsivt layout.

**Apache License 2.0 gælder kildekoden, ikke UCN-logoet eller det leverede favicon.** Se `NOTICE`. Brug af branding er ikke en godkendelse eller certificering af ProxPortal fra UCN.

## Kompatibilitet

Den synlige standardtitel er ændret fra LabPortalen til ProxPortal. Databasens skema, tekniske filnavne, sessionscookie, Docker-projektnavn, volumen og eksisterende sagsnumre er bevaret, så en opgradering ikke skjuler en eksisterende database. En eksisterende installation skal selv ændre `PORTAL_NAME` i `.env` til `ProxPortal`.
