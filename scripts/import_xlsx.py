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


def rating_parts(professional: str) -> dict:
    """The numbers behind a credential string, so the list can be ordered by it.

    A rating string can name more than one body - Jacques Chaput carries two stars from
    Guide Hachette and three from 1001 Dégustations - so every star count in the string
    is collected and the best one is used.
    """
    stars = [int(n) for n in re.findall(r"(\d+)\s*stars?", professional, re.IGNORECASE)]
    points = [int(n) for n in re.findall(r"(\d+)\s*(?:pts|points)", professional, re.IGNORECASE)]
    return {
        "stars": max(stars) if stars else None,
        "points": max(points) if points else None,
        "coup_de_coeur": "coup de c" in professional.lower(),
    }


def rating_rank(parts: dict) -> float:
    """How strongly a wine is credentialled, for sorting. Higher is better.

    Guide Hachette stars and a critic's point score are not the same scale and cannot be
    made into one, so this is a judgement stated plainly rather than a calculation:

      * the best star count any professional guide awarded, plus
      * half a point for a Coup de Cœur - the guide's own top distinction, given to
        roughly six wines nationally, so it outranks the stars beside it;
      * where only a point score exists, it stands in for a star count: 96+ sits just
        under three stars, 90-95 just over two.

    A wine with no professional rating scores zero and sorts below every wine that has
    one, which is the only part of this that is not a judgement.
    """
    if parts["stars"] is not None:
        return parts["stars"] + (0.5 if parts["coup_de_coeur"] else 0.0)
    if parts["points"] is not None:
        return 2.8 if parts["points"] >= 96 else (2.3 if parts["points"] >= 90 else 1.5)
    return 0.0


def score_tier(professional: str) -> str:
    if not professional:
        return "none"
    return "verified" if _VERIFIED.search(professional) else "listed"


def headline_score(professional: str, tier: str, parts: dict | None = None) -> str:
    """The one short string the gallery card shows.

    Long enough to be honest, short enough to sit on a card - the full text is on the
    detail page.
    """
    if tier == "none":
        return ""
    parts = parts or rating_parts(professional)
    # Hachette's own star count, which is what the badge names - not the best count from
    # any guide, which would attribute another body's rating to Hachette.
    hachette = re.search(r"(\d+)\s*stars?[^;]*guide hachette", professional, re.IGNORECASE)
    stars = hachette.group(1) if hachette else (parts["stars"] and str(parts["stars"]))
    if stars and parts["coup_de_coeur"]:
        return f"{stars}★ + Coup de Cœur"
    if stars:
        return f"{stars}★ Guide Hachette"
    if parts["points"]:
        source = "Decanter" if "decanter" in professional.lower() else "critic"
        return f"{parts['points']} pts ({source})"
    return "Guide Hachette listed"


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
        tier = score_tier(professional)

        # Match the photograph on producer *and* cuvée where a producer has two wines.
        candidates = [i for i in images if i["keys"] & words]
        if len(candidates) > 1:
            cuvee_words = key_words(cuvee)
            candidates.sort(key=lambda i: len(i["cuvee_keys"] & cuvee_words), reverse=True)
        image = candidates[0] if candidates else {}
        visit = matching(visits, words)
        prices = matching(comparisons, words, first_only=False)
        parts = rating_parts(professional)
        rank = rating_rank(parts)
        if tier == "listed":
            # Named by the guide but with the star count unconfirmed: ranked above the
            # wines with nothing, below every wine whose rating was actually pinned down.
            rank = 0.25

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
            "headline_score": headline_score(professional, tier, parts),
            "stars": parts["stars"],
            "points": parts["points"],
            "coup_de_coeur": parts["coup_de_coeur"],
            "rating_rank": rank,
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
