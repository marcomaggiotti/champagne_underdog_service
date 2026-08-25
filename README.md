# Champagne Underdogs

A showcase for sixteen grower Champagnes under €40 — the ones with real credentials and
no marketing budget. Built from a research spreadsheet, deployed on Render as a web
service.

**It is not a shop.** There is no basket, no checkout and no affiliate link. Prices are
research figures shown so a reader can see what a bottle costs at the property. Every
visitor confirms they are of legal drinking age before anything is shown.

## Running it

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://127.0.0.1:8000
```

| Route | What it is |
| --- | --- |
| `/` | the gallery — bottle, name, price and rating for each wine |
| `/champagne/{slug}` | one wine in full: description, facts, what was verified, visiting details, prices elsewhere |
| `/api/champagnes` | the catalogue as JSON, the same data the pages render from |
| `/health` | Render's health check; reports how many wines loaded |

## Deploying

`render.yaml` is a Render Blueprint. New → Blueprint → point it at this repo. Nothing
needs configuring: the catalogue is committed, so there is no database, no key and no
external call. On the free plan the service sleeps after 15 minutes idle and takes about
50 seconds to wake.

## Updating the wines

`data/champagnes.json` is the source of truth for the site. Regenerate it from the
workbook:

```bash
python scripts/import_xlsx.py path/to/champagneshortlist.xlsx
```

Then commit the JSON and redeploy. Editing the JSON by hand is fine for a price
correction.

## Three decisions worth knowing about

### The list is ordered by credential, not by price

The default order is strongest professional rating first. Guide Hachette stars and a
critic's point score are not the same scale and cannot honestly be made into one, so the
ordering is a stated judgement rather than a calculation:

- the best star count **any** professional guide awarded, plus
- half a point for a **Coup de Cœur** — the guide's own top distinction, given to about
  six wines nationally, so it outranks the stars beside it;
- where only a point score exists it stands in for a star count: 96+ just under three
  stars, 90–95 just over two;
- wines the guide only *lists* follow, then wines with no professional rating at all.

Which puts Jacques Chaput first: two Hachette stars **and** a Coup de Cœur, plus three
stars from 1001 Dégustations. Its badge still reads "2★ + Coup de Cœur", because that is
what Hachette itself gave — the badge names one body and must not credit it with
another's stars.

`/?sort=price` restores cheapest-first, and the control is on the page.

### The ratings are tiered, not averaged

The workbook divides the list three ways, and the site keeps that division rather than
flattening it into one number:

| Shown as | Meaning |
| --- | --- |
| gold badge | a professional rating that was verified — Guide Hachette stars, or a critic's point score |
| dashed badge | the wine appears in Guide Hachette but the star count could not be confirmed |
| plain badge | no professional rating was found |

Ten of the sixteen fall in the last two groups. A single "score" column would have
implied a rating for all of them, which the workbook explicitly warns against: *"No
professional rating found. Do not imply one."*

A retailer's customer rating is shown separately again, and labelled as such — it is not
a professional score and the workbook says to keep it visually apart from one.

Every wine's page carries its verification note, so the reader can see exactly what was
and was not confirmed.

### Photographs, with a drawn bottle underneath

Fifteen of the sixteen wines now carry a bottle photograph from the workbook's Images
sheet, and the site shows it. The sixteenth — Besserat de Bellefon — has none, and says
so on its page.

Behind every photograph sits a drawn SVG bottle (`app/bottles.py`), and it is what
renders whenever the photograph does not. That is not decoration. The workbook is blunt
about the risk: *"Hotlinking is also fragile — the host can block it or change the path
and your live product page shows a broken image."* Until the files are downloaded they
are hotlinked, so the fallback is the difference between a missing bottle and a hole in
the grid.

The drawings are deterministic — the foil capsule is keyed to the producer, the label
accent to the style — so a blanc de blancs and a blanc de noirs stay distinguishable
even when every photograph fails.

**Stop hotlinking as soon as you can:**

```bash
python scripts/fetch_images.py
```

That downloads the photographs into `app/static/bottles/`, and the site prefers a local
file over a remote URL automatically — no other change needed. Commit what lands there.

Downloading is not permission. These photographs belong to the retailer or the producer,
and the workbook's route is the right one: ask each grower for written permission, or
shoot your own bottles on the buying trip. Each wine's page links to its producer.

## Layout

```
app/
  main.py          FastAPI: gallery, detail, health, JSON
  bottles.py       the SVG bottle generator
  templates/       base (with the age gate), index, detail, 404
  static/          style.css, age-gate.js
  static/bottles/  downloaded photographs (empty until you fetch them)
data/champagnes.json   the catalogue
scripts/import_xlsx.py workbook -> catalogue
scripts/fetch_images.py download the photographs so the site stops hotlinking
render.yaml            the Blueprint
```

## Before this goes live

The workbook flags two things this repo cannot decide for you:

- **Prices were retrieved on 25 August 2026 and several were sale prices.** Re-verify.
- **The photographs are hotlinked until you run `scripts/fetch_images.py`,** and they
  belong to the retailer or the producer either way. Get permission, or take your own.
  The `hachette-vins.shop` URLs carry a `?ts=` cache-buster that changes when they
  re-upload, so those in particular should be re-checked before launch.
- **Check your jurisdiction's rules on alcohol advertising and age-gating.** The gate
  here is a self-declaration stored in the visitor's browser, which is the common
  approach but not the same thing as verification.
