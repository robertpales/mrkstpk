# marekstopka.com

Statický portfólio web fotografa Mareka Stopku: jeden `index.html`, bez build kroku a bez frameworku.

## Štruktúra
- `index.html`: celá stránka (HTML + inline CSS/JS)
- `img/<kategória>/...`: optimalizované fotky `.webp`. Názvy obsahujú hash (napr. `-d1739be1-1600.webp`), takže sa dajú cachovať natrvalo. Keď sa fotka zmení, musí dostať nový názov.
- `fonts/`: Inter (woff2)
- `sitemap.xml`: obsahuje aj zoznam obrázkov. Pri pridaní alebo odstránení fotiek ho treba aktualizovať.
- `.htaccess`: HTTPS presmerovanie a cache hlavičky (LiteSpeed/Apache)
- `web/`, `web-full/`: originálne JPG fotky. Sú len lokálne, nie sú v gite ani na webe.

## Deploy
Každý `git push` do vetvy `master` sa **automaticky nasadí na živý web** (GitHub Actions → rsync cez SSH na hosting Spaceship, pozri `.github/workflows/deploy.yml`).
- Pred pushom over zmeny lokálne (otvor `index.html` v prehliadači).
- Deploy nič na serveri nemaže. Keď sa súbor z repa odstráni, na hostingu zostane, kým ho niekto nezmaže ručne.
- Stav deployu: `gh run list` / záložka Actions na GitHube.

## Pravidlá
- Nové fotky konvertuj do `.webp` a vlož do `img/<kategória>/`. Do repa nedávaj veľké JPG.
- Pred commitom urob `git pull`, na repe pracujú dvaja ľudia.
