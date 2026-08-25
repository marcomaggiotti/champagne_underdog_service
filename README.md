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

## Two decisions worth knowing about

### The ratings are tiered, not averaged

The workbook divides the list three ways, and the site keeps that division rather than
flattening it into one number:

| Shown as | Meaning |
| --- | --- |
| gold badge | a professional rating that was verified — Guide Hachette stars, or a critic's point score |
| dashed badge | the wine appears in Guide Hachette but the star count could not be confirmed |
| plain badge | no professional rating was found |

Eleven of the sixteen fall in the last two groups. A single "score" column would have
implied a rating for all of them, which the workbook explicitly warns against: *"No
professional rating found. Do not imply one."*

A retailer's customer rating is shown separately again, and labelled as such — it is not
a professional score and the workbook says to keep it visually apart from one.

Every wine's page carries its verification note, so the reader can see exactly what was
and was not confirmed.

### The bottles are drawn, not photographed

The workbook's Images sheet opens with **"YOU CANNOT JUST COPY THESE IMAGES ONTO YOUR
SITE"**: retailer and producer photographs belong to whoever shot them, and hotlinking
them invites a broken image the day the host changes a path. Of the sixteen wines
exactly one has a verified image URL.

So `app/bottles.py` draws an SVG bottle per wine — deterministic, with the foil capsule
keyed to the producer and the label accent to the style, so a blanc de blancs and a
blanc de noirs are distinguishable in the grid. No permissions to chase, nothing to
break, and a consistent look sixteen scraped photos would never have had.

Each wine's page links to the producer, so real images can be requested. The workbook's
own advice: ask the grower on the buying trip, or shoot your own — you will have the
bottles.

## Layout

```
app/
  main.py          FastAPI: gallery, detail, health, JSON
  bottles.py       the SVG bottle generator
  templates/       base (with the age gate), index, detail, 404
  static/          style.css, age-gate.js
data/champagnes.json   the catalogue
scripts/import_xlsx.py workbook -> catalogue
render.yaml            the Blueprint
```

## Before this goes live

The workbook flags two things this repo cannot decide for you:

- **Prices were retrieved on 25 August 2026 and several were sale prices.** Re-verify.
- **Check your jurisdiction's rules on alcohol advertising and age-gating.** The gate
  here is a self-declaration stored in the visitor's browser, which is the common
  approach but not the same thing as verification.
