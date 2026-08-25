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

# A number attached to "stars", "pts" or "points" is a real rating. A bare year in
# "Guide Hachette 2026 (listed)" is not, which is the whole distinction the legend draws.
_VERIFIED = re.compile(r"\b\d+\s*(?:stars?|pts|points)\b|coup de c", re.IGNORECASE)
_EMPTY = {"", "—", "-", "not specified", "none", "n/a", "(not found)", "(no site listed)"}


def clean(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in _EMPTY else text


def number(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def key_words(name: str) -> set[str]:
    """Surnames, for matching a wine to its producer across sheets.

    The sheets disagree on spelling - "Cyril Banchet" in one, "Cyrill Banchet" in
    another - so matching on the whole string silently drops the visit details.
    """
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    stop = {"champagne", "and", "fils", "et", "de", "la", "le", "du", "des"}
    return {w for w in re.findall(r"[a-z]+", plain) if len(w) >= 4 and w not in stop}


def score_tier(professional: str) -> str:
    if not professional:
        return "none"
    return "verified" if _VERIFIED.search(professional) else "listed"


def headline_score(professional: str, tier: str) -> str:
    """The one short string the gallery card shows.

    Long enough to be honest, short enough to sit on a card - the full text is on the
    detail page.
    """
    if tier == "none":
        return ""
    stars = re.search(r"(\d+)\s*stars?", professional, re.IGNORECASE)
    points = re.search(r"(\d+)\s*(?:pts|points)", professional, re.IGNORECASE)
    coup = "coup de c" in professional.lower()
    if stars and coup:
        return f"{stars.group(1)}★ + Coup de Cœur"
    if stars:
        return f"{stars.group(1)}★ Guide Hachette"
    if points:
        source = "Decanter" if "decanter" in professional.lower() else "critic"
        return f"{points.group(1)} pts ({source})"
    return "Guide Hachette listed"


def rows_of(worksheet, header_row: int = 0) -> list[dict]:
    raw = [r for r in worksheet.iter_rows(values_only=True)
           if any(c is not None and str(c).strip() for c in r)]
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

    # --- image rights position, keyed the same way --------------------------------
    images = []
    for row in rows_of(book["Images"], header_row=11):
        producer = clean(row.get("Producer"))
        if not producer or producer.lower() == "producer":
            continue
        images.append({
            "keys": key_words(producer),
            "cuvee": clean(row.get("Cuvée")),
            "verified_url": clean(row.get("Verified image URL (resolves)")),
            "product_page": clean(row.get("Product page (image is here)")),
            "producer_site": clean(row.get("Producer official site (ask for rights here)")),
            "phone": clean(row.get("Producer phone")),
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
        tier = score_tier(professional)

        image = matching(images, words) or {}
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
            "professional_score": professional,
            "score_tier": tier,
            "headline_score": headline_score(professional, tier),
            "medals": clean(row.get("Medals / Awards")),
            "retailer_rating": number(row.get("Retailer Rating (/5)")),
            "description": clean(row.get("Website Description (ready to publish)")),
            "product_url": clean(row.get("Product URL")),
            "verification_note": clean(row.get("Verification Note")),
            "image_rights": {k: v for k, v in image.items() if k != "keys"},
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
    print(f"  with a verified image URL: "
          f"{sum(1 for w in data['wines'] if w['image_rights'].get('verified_url'))}")


if __name__ == "__main__":
    main()
