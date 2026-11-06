# marekstopka.com

Statický portfólio web fotografa Mareka Stopku: jeden `index.html`, bez frameworku. Fotky, zoznam albumov, SEO hlavičku a sitemap generuje skript `tools/build_site.py`.

## Ako robiť zmeny (postup)
1. Raz na začiatku: `git clone https://github.com/robertpales/mrkstpk` a otvor priečinok v Claude Code.
2. Pred každou prácou: `git pull`
3. Povedz Claudovi, čo chceš zmeniť (text, fotky, sekcie...).
4. Skontroluj výsledok: otvor `index.html` v prehliadači.
5. Keď je to OK, povedz Claudovi „commitni a pushni“ (alebo Commit + Push v GitHub Desktop). Do pár sekúnd je zmena na webe.

Ak sa niečo pokazí, stačí vrátiť posledný commit (`git revert HEAD`) a pushnúť.

## Fotky (len na Marekovom PC)
Originály nie sú v gite. Ležia vedľa repa: `../fotky/<KATEGÓRIA>/<album>/*.jpg`
(`KATEGÓRIA` = AUTOMOTIVE, EVENTS, GASTRO, LIFESTYLE). Po zmene fotiek spusti:

    python3 tools/build_site.py        # opakuj, kým nevypíše DONE

Skript vyrobí `img/` (WebP 480/960/1600 px s hashom v názve), prepíše zoznam `ALBUMS` a blok
`<!--BUILD:HEAD-->` v `index.html`, `sitemap.xml`, `robots.txt`, `.htaccess`, favicony a `og-image-*.jpg`,
a zmaže z `img/` fotky, ktoré už nie sú v `../fotky`. Tieto časti needituj ručne, prepíšu sa.

Pravidlá pomenovania:
- poradie albumov: číslo na začiatku priečinka (`10 JAGUAR F-TYPE`, `20 …`; nový medzi = `15 …`)
- poradie fotiek v albume: `1.jpg, 2.jpg … 10.jpg`
- záložka ALL: `_top<číslo>` na konci názvu súboru (`3_top4.jpg` = 4. pozícia v ALL)
- celý riadok v ALL (6 fotiek): `_row<číslo>` (`7_row1.jpg` = 1. riadok)
- fotka v sekcii O mne: `../me*.jpg`, favicon: `../FAVICON_logo.png` (biela značka, priehľadné pozadie)
- export z Lightroomu v sRGB (iné profily skript prevedie, ale sRGB je istota)

## Štruktúra
- `index.html`: celá stránka (HTML + inline CSS/JS)
- `img/<kategória>/<album>/...`: optimalizované fotky `.webp`. Názvy obsahujú hash (napr. `-d1739be1-1600.webp`), takže sa dajú cachovať natrvalo. Keď sa fotka zmení, dostane nový názov automaticky.
- `fonts/`: Inter (woff2)
- `sitemap.xml`: obsahuje aj zoznam obrázkov (generuje skript)
- `.htaccess`: HTTPS presmerovanie, cache hlavičky, presmerovanie starého `/portfolio` (LiteSpeed/Apache)
- `tools/`: build skript, na server sa nenahráva

## Deploy
Každý `git push` do vetvy `master` sa **automaticky nasadí na živý web** (GitHub Actions → rsync cez SSH na hosting Spaceship, pozri `.github/workflows/deploy.yml`).
- Pred pushom over zmeny lokálne (otvor `index.html` v prehliadači).
- Deploy nič na serveri nemaže. Keď sa súbor z repa odstráni (napr. stará fotka z `img/`), na hostingu zostane, kým ho niekto nezmaže ručne.
- Stav deployu: `gh run list` / záložka Actions na GitHube.

## Pravidlá
- Fotky nekonvertuj ručne a nedávaj do repa veľké JPG. Vždy cez `tools/build_site.py`.
- Pred commitom urob `git pull`, na repe pracujú dvaja ľudia.
