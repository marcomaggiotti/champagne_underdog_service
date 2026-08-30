#!/usr/bin/env python3
"""Turn the champagne shortlist workbook into the JSON the site is built from.

Run this when the spreadsheet changes:

    python scripts/import_xlsx.py path/to/champagneshortlist.xlsx

Two things in here are judgement, not transcription, and both come from rules the
workbook states about itself:

Ratings are tiered by how well they are evidenced. The workbook's own legend divides
the list into wines with a verified professional rating (Guide Hachette stars or a
critic point score), wines merely *listed* by Hachette with the star count unconfirmed,
and wines with no professional rating at all - followed by the instruction "Do not imply
one". So the tier is derived here and the site renders the three differently, rather
than flattening them into a single "score" that would overstate two thirds of the list.

The retailer rating is carried separately for the same reason: the workbook calls it
"Champagne Terroir's own customer rating. NOT a professional score. Keep it visually
separate on the site."
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    import openpyxl
except ImportError:  # pragma: no cover - the script's only dependency
    sys.exit("openpyxl is required:  pip install openpyxl")

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "champagnes.json"

# Run as `python scripts/import_xlsx.py`, it is scripts/ that lands on the path, not the
# repo - so put the repo there before importing from app.
sys.path.insert(0, str(REPO))

# The rating rules are the site's, not this script's: a wine typed into /admin has to be
# tiered and ranked identically to one imported here, or the gallery's order stops
# meaning one thing. See app/ratings.py.
from app.ratings import derive, slugify  # noqa: E402

_EMPTY = {"", "—", "-", "not specified", "none", "n/a", "(not found)", "(no site listed)"}


def clean(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in _EMPTY else text


def number(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def key_words(name: str) -> set[str]:
    """Surnames, for matching a wine to its producer across sheets.

    The sheets disagree on spelling - "Cyril Banchet" in one, "Cyrill Banchet" in
    another - so matching on the whole string silently drops the visit details.
    """
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    stop = {"champagne", "and", "fils", "et", "de", "la", "le", "du", "des"}
    return {w for w in re.findall(r"[a-z]+", plain) if len(w) >= 4 and w not in stop}


def rows_of(worksheet, header_row: int = 0, header_starts_with: str = "") -> list[dict]:
    """Rows as dicts, keyed by a header row.

    Blank rows are dropped first, so `header_row` counts non-empty rows - not sheet
    rows. Pass `header_starts_with` instead when the header can move between workbook
    revisions: an off-by-one here does not fail, it silently keys every row by the
    wrong column names.
    """
    raw = [r for r in worksheet.iter_rows(values_only=True)
           if any(c is not None and str(c).strip() for c in r)]
    if header_starts_with:
        header_row = next(
            (i for i, row in enumerate(raw) if clean(row[0]) == header_starts_with),
            header_row,
        )
    header = [clean(c) or f"col{i}" for i, c in enumerate(raw[header_row])]
    return [dict(zip(header, row)) for row in raw[header_row + 1:]]


def load(path: Path) -> dict:
    book = openpyxl.load_workbook(path, data_only=True)

    # --- visit details, keyed by producer surname ---------------------------------
    visits = []
    for row in rows_of(book["Itinerary & Addresses"]):
        producer = clean(row.get("Producer"))
        if not producer or not clean(row.get("Address")):
            continue  # the sheet's prose rows sit under the table
        visits.append({
            "keys": key_words(producer),
            "name": producer,
            "address": clean(row.get("Address")),
            "region": clean(row.get("Village / Sub-region")),
            "phone": clean(row.get("Phone")),
            "website": clean(row.get("Website")),
            "hours": clean(row.get("Opening hours")),
            "credential": clean(row.get("Credential")),
            "booking_risk": clean(row.get("Booking risk")),
            "lat": number(row.get("Lat")),
            "lon": number(row.get("Lon")),
        })

    # --- bottle photographs --------------------------------------------------------
    # The header row moved between workbook revisions, so find it rather than hard-code
    # a row number - an off-by-one here silently produces sixteen wines with no image.
    images = []
    for row in rows_of(book["Images"], header_starts_with="Producer"):
        producer = clean(row.get("Producer"))
        if not producer:
            continue
        cuvee = clean(row.get("Cuvée"))
        if not cuvee:
            continue  # the sheet's prose notes sit under the table
        hires = clean(row.get("High-resolution variant"))
        images.append({
            # Two Olivier Rousseaux cuvées share a producer, so the cuvée has to take
            # part in the match or both wines get the first one's photograph.
            "keys": key_words(producer),
            "cuvee_keys": key_words(cuvee),
            "cuvee": cuvee,
            "url": clean(row.get("IMAGE URL (verified, as observed)")),
            # "(single size served)" is a note, not a URL.
            "hires": hires if hires.startswith("http") else "",
            "host": clean(row.get("Host")),
            "status": clean(row.get("Status")),
        })

    # --- alternative prices --------------------------------------------------------
    comparisons: list[dict] = []
    for row in rows_of(book["Price Comparison"]):
        wine = clean(row.get("Wine"))
        if not wine or not clean(row.get("Retailer / Site")):
            continue
        comparisons.append({
            "keys": key_words(wine),
            "wine": wine,
            "retailer": clean(row.get("Retailer / Site")),
            "country": clean(row.get("Country")),
            "price": clean(row.get("Price")),
            "eur": number(row.get("In EUR (approx)")),
            "notes": clean(row.get("Notes")),
            "url": clean(row.get("URL")),
        })

    def matching(pool: list[dict], words: set[str], first_only: bool = True):
        hits = [entry for entry in pool if entry["keys"] & words]
        if not hits:
            return None if first_only else []
        return hits[0] if first_only else hits

    wines = []
    for row in rows_of(book["Champagne Shortlist"]):
        producer, cuvee = clean(row.get("Producer")), clean(row.get("Cuvée"))
        if not producer:
            continue
        words = key_words(producer)
        professional = clean(row.get("Professional Score / Rating"))

        # Match the photograph on producer *and* cuvée where a producer has two wines.
        candidates = [i for i in images if i["keys"] & words]
        if len(candidates) > 1:
            cuvee_words = key_words(cuvee)
            candidates.sort(key=lambda i: len(i["cuvee_keys"] & cuvee_words), reverse=True)
        image = candidates[0] if candidates else {}
        visit = matching(visits, words)
        prices = matching(comparisons, words, first_only=False)

        wines.append({
            "id": int(float(row["#"])),
            "slug": slugify(f"{producer}-{cuvee}"),
            "producer": producer,
            "cuvee": cuvee,
            "village": clean(row.get("Village / Region")),
            "classification": clean(row.get("Classification")),
            "style": clean(row.get("Style / Grapes")),
            "price_eur": number(row.get("Price (EUR)")),
            # professional_score, score_tier, headline_score, stars, points,
            # coup_de_coeur and rating_rank, all from the one credential string.
            **derive(professional),
            "medals": clean(row.get("Medals / Awards")),
            "retailer_rating": number(row.get("Retailer Rating (/5)")),
            "description": clean(row.get("Website Description (ready to publish)")),
            "product_url": clean(row.get("Product URL")),
            "verification_note": clean(row.get("Verification Note")),
            "image": {k: v for k, v in image.items() if k not in ("keys", "cuvee_keys")},
            "visit": {k: v for k, v in visit.items() if k != "keys"} if visit else None,
            "other_prices": [{k: v for k, v in p.items() if k != "keys"} for p in prices],
        })

    notes = {clean(r.get("Field")): clean(r.get("Detail"))
             for r in rows_of(book["Sources & Notes"]) if clean(r.get("Field"))}

    return {"wines": wines, "notes": notes}


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not source or not source.exists():
        sys.exit("usage: python scripts/import_xlsx.py <champagneshortlist.xlsx>")
    data = load(source)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    tiers: dict[str, int] = {}
    for wine in data["wines"]:
        tiers[wine["score_tier"]] = tiers.get(wine["score_tier"], 0) + 1
    print(f"wrote {OUT.relative_to(REPO)}: {len(data['wines'])} wines")
    print(f"  rating tiers: {tiers}")
    print(f"  with visit details: {sum(1 for w in data['wines'] if w['visit'])}")
    print(f"  with a bottle photograph: "
          f"{sum(1 for w in data['wines'] if w['image'].get('url'))}")


if __name__ == "__main__":
    main()
