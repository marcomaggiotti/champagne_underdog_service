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
| `/` | the gallery — bottle, name, price and rating for each wine, and a map of the growers |
| `/champagne/{slug}` | one wine in full: description, facts, what was verified, visiting details, prices elsewhere |
| `/admin` | add a wine to the list. **Behind a login** — see below |
| `/api/champagnes` | the catalogue as JSON, the same data the pages render from |
| `/api/winehouses` | the map's pins: one per house, with whichever of its wines are on the list |
| `/health` | Render's health check; reports how many wines loaded |

## Adding a wine

`/admin` is a form that writes straight into `data/champagnes.json`; the wine is in the
gallery on the next request. It is behind HTTP Basic auth:

| | |
| --- | --- |
| user | `admin` |
| password | `maorvelous` |

**Change them before this is reachable from the internet.** That pair is the default
because it was the one asked for, and it is written down in a public repository, which
makes it a published password rather than a secret one. `ADMIN_USER` and
`ADMIN_PASSWORD` override it, and `render.yaml` asks Render for both:

```bash
ADMIN_USER=marco ADMIN_PASSWORD='something nobody has read' uvicorn app.main:app
```

**On Render's free plan, a wine added through the form does not survive a deploy.** The
disk is ephemeral and the checkout goes back to what is committed. Two ways out: mount a
persistent disk and point `CHAMPAGNE_DATA` at a file on it, or use the form to draft the
wine, then copy `data/champagnes.json` back into the repo and commit it.

One thing the form deliberately cannot do is assert a rating. There is no "tier" control:
you type the credential as the guide states it — *"2 stars + Coup de Cœur, Guide Hachette
2026"* — and the tier, the ranking and the badge are read off that text by
`app/ratings.py`, which is the same code the workbook importer uses. A gold badge is
supposed to mean somebody verified a rating; a tick-box marked "verified" would be a way
of claiming one without having done so. Leave the field empty and the wine reads "No
rating found", which is the honest answer and costs it nothing but its place in the
order.

## The map

The front page maps every grower whose address the workbook confirmed — nine houses, one
pin each. Three of the sixteen wines come from Olivier Rousseaux's cellar in Verzenay, so
the pins are grouped by address rather than drawn per wine; a pin's info window lists
whichever of its wines are on the list.

Google Maps needs an API key. Set `GOOGLE_MAPS_API_KEY` and the map appears:

```bash
GOOGLE_MAPS_API_KEY=AIza... uvicorn app.main:app --reload
```

Without one, the page says the map is switched off and shows the same houses as a list of
addresses, phone numbers and Google Maps links. That list is always rendered, under the
map when there is one: it is the part that survives a blocked script, a spent quota and
scripting switched off, and an address and a phone number are what you actually need in
order to visit somebody. A keyless Google map is a grey rectangle stamped *"for
development purposes only"*, which is worse than no map at all.

Google's script is only fetched once a visitor has confirmed their age — the map sits
inside the gated part of the page, and a map initialised inside a hidden element measures
zero and renders grey for good. So it waits for the gate to lift, which also means a
visitor who never confirms never loads anything from Google.

## Deploying

`render.yaml` is a Render Blueprint. New → Blueprint → point it at this repo. The public
site needs nothing configured: the catalogue is committed, so there is no database and no
external call. Set `GOOGLE_MAPS_API_KEY` for the map and `ADMIN_USER` / `ADMIN_PASSWORD`
for the form — the Blueprint asks for all three. On the free plan the service sleeps after
15 minutes idle and takes about 50 seconds to wake.

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
  catalogue.py     the catalogue file - reading it, adding to it, writing it back
  admin.py         /admin: the login and the add form
  ratings.py       credential text -> tier, rank and badge (shared with the importer)
  winehouses.py    wines -> one map pin per address
  bottles.py       the SVG bottle generator
  templates/       base (with the age gate), index, detail, admin, the map, 404
  static/          style.css, age-gate.js, map.js
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
- **Change the `/admin` password**, and know what the login is and is not. HTTP Basic
  sends the password on every request, so it is only as private as the connection —
  fine over Render's HTTPS, not fine over plain HTTP. It is a lock on a page one person
  uses, not an account system: there is no rate limiting, no lockout and no audit trail
  of who added what.
- **Restrict the Google Maps key** to your domain in the Google Cloud console before you
  ship it. A browser key is public by definition — it is in the page source — and an
  unrestricted one is somebody else's map quota, billed to you.
