"""The catalogue file: reading it, adding to it, writing it back.

Until now the JSON was read-only - regenerated from the workbook, committed, deployed.
/admin makes it writable at runtime, which brings three things with it that the read
path never had to think about, and they are all handled here rather than in the view:

*   **The cache has to be dropped on write.** The site reads the file once per process,
    which is correct for a file that only changes at deploy time and wrong the moment
    one does not.
*   **A half-written catalogue must never exist.** The file is written to a temporary
    file beside it and moved into place, so a crash mid-write leaves the old catalogue
    intact rather than a truncated one the health check then refuses to serve.
*   **The invariants the file carries have to survive an insert.** It is stored
    cheapest-first and numbered from one, and the site shows both ("No. 4 of 17"), so
    adding a wine re-sorts and re-numbers rather than appending to the end.

Where the file lives is configurable through CHAMPAGNE_DATA. That matters on Render:
the checkout is ephemeral, so a wine added on the running service is lost at the next
deploy unless this points at a mounted disk. See the README.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .ratings import derive, slugify

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("CHAMPAGNE_DATA") or (BASE.parent / "data" / "champagnes.json"))


class ValidationError(Exception):
    """What the form got wrong, keyed by field name so each input can say so itself."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


@lru_cache(maxsize=1)
def load_data() -> dict[str, Any]:
    """Read the catalogue once per process, until something writes to it."""
    if not DATA.exists():
        raise RuntimeError(
            f"{DATA} is missing. Generate it with:\n"
            f"    python scripts/import_xlsx.py <champagneshortlist.xlsx>"
        )
    return json.loads(DATA.read_text(encoding="utf-8"))


def wines() -> list[dict[str, Any]]:
    return load_data()["wines"]


def find(slug: str) -> dict[str, Any] | None:
    return next((w for w in wines() if w["slug"] == slug), None)


def save_data(data: dict[str, Any]) -> None:
    """Replace the catalogue, atomically, and forget the cached copy."""
    DATA.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    # Same directory as the target: os.replace is only atomic within one filesystem.
    handle, temporary = tempfile.mkstemp(dir=DATA.parent, prefix=".champagnes-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(body)
        os.replace(temporary, DATA)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    load_data.cache_clear()


# --- validation -----------------------------------------------------------------------

def _text(form: dict[str, Any], field: str) -> str:
    return str(form.get(field) or "").strip()


def _number(form: dict[str, Any], field: str) -> float | None:
    """A decimal, comma or point. ValueError is caught by the caller and shown as a hint.

    "nan" and "1e400" are both floats to Python and neither is JSON: written out they
    become the bare tokens NaN and Infinity, which every strict reader of this file - the
    JSON API's own consumers included - is entitled to reject. They are refused here,
    where the message still lands next to the input that caused them.
    """
    raw = _text(form, field).replace(",", ".")
    if not raw:
        return None
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("not a number")
    return round(value, 4)


def _link(raw: str) -> str:
    """A URL we are willing to put in an href.

    Every URL on this form ends up in a link or an <img src>, and Jinja's escaping does
    not make `javascript:...` safe there - it is a valid attribute value. Only http and
    https get through.
    """
    if not raw:
        return ""
    if urlparse(raw).scheme not in ("http", "https"):
        raise ValueError("must start with http:// or https://")
    return raw


def unique_slug(base: str, taken: set[str]) -> str:
    """`sonnette-brut-tradition`, then `-2`, `-3`. Two growers do share a name here."""
    slug = base or "champagne"
    if slug not in taken:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in taken:
        suffix += 1
    return f"{slug}-{suffix}"


def build_wine(form: dict[str, Any], taken: set[str] | None = None) -> dict[str, Any]:
    """A form submission as a catalogue record, or ValidationError saying why not.

    The rating fields are not taken from the form: they are derived from the credential
    string by app/ratings.py, the same way the importer derives them. There is no input
    for "tier" precisely because it is not a thing anyone should be able to assert - it
    is a reading of the evidence, and the evidence is the text.
    """
    errors: dict[str, str] = {}

    producer = _text(form, "producer")
    cuvee = _text(form, "cuvee")
    if not producer:
        errors["producer"] = "Who made it? This one is required."
    if not cuvee:
        errors["cuvee"] = "Which cuvée? This one is required."

    price = None
    if not _text(form, "price_eur"):
        errors["price_eur"] = "The price at the property is the point of the list."
    else:
        try:
            price = _number(form, "price_eur")
            if price is None or price <= 0:
                errors["price_eur"] = "A price in euros, greater than zero."
        except ValueError:
            errors["price_eur"] = "A number, please — 26.50, not “about €26”."

    retailer_rating = None
    try:
        retailer_rating = _number(form, "retailer_rating")
        if retailer_rating is not None and not 0 <= retailer_rating <= 5:
            errors["retailer_rating"] = "A customer rating out of 5."
    except ValueError:
        errors["retailer_rating"] = "A number out of 5, or leave it empty."

    links: dict[str, str] = {}
    for field in ("product_url", "image_url", "visit_website"):
        try:
            links[field] = _link(_text(form, field))
        except ValueError as exc:
            errors[field] = str(exc)

    # Both or neither: one half of a coordinate puts a pin in the sea.
    lat = lon = None
    try:
        lat = _number(form, "visit_lat")
        if lat is not None and not -90 <= lat <= 90:
            errors["visit_lat"] = "A latitude between -90 and 90."
    except ValueError:
        errors["visit_lat"] = "A decimal latitude, e.g. 49.04."
    try:
        lon = _number(form, "visit_lon")
        if lon is not None and not -180 <= lon <= 180:
            errors["visit_lon"] = "A longitude between -180 and 180."
    except ValueError:
        errors["visit_lon"] = "A decimal longitude, e.g. 3.96."
    if "visit_lat" not in errors and "visit_lon" not in errors and (lat is None) != (lon is None):
        missing = "visit_lon" if lon is None else "visit_lat"
        errors[missing] = "Latitude and longitude go together — the map needs both."

    if errors:
        raise ValidationError(errors)

    image_url = links["image_url"]
    visit_fields = ("visit_name", "visit_address", "visit_region", "visit_phone",
                    "visit_hours", "visit_credential", "visit_booking_risk")
    has_visit = any(_text(form, f) for f in visit_fields) or links["visit_website"] or lat is not None

    wine = {
        "id": 0,                                    # assigned when it is filed
        "slug": unique_slug(slugify(f"{producer}-{cuvee}"), taken or set()),
        "producer": producer,
        "cuvee": cuvee,
        "village": _text(form, "village"),
        "classification": _text(form, "classification"),
        "style": _text(form, "style"),
        "price_eur": price,
        # professional_score, score_tier, headline_score, stars, points, coup_de_coeur
        # and rating_rank, all read off the one credential string.
        **derive(_text(form, "professional_score")),
        "medals": _text(form, "medals"),
        "retailer_rating": retailer_rating,
        "description": _text(form, "description"),
        "product_url": links["product_url"],
        "verification_note": _text(form, "verification_note"),
        "image": {
            "cuvee": cuvee,
            "url": image_url,
            "hires": "",
            "host": urlparse(image_url).hostname or "" if image_url else "",
            "status": _text(form, "image_status"),
        },
        "visit": {
            "name": _text(form, "visit_name") or f"Champagne {producer}",
            "address": _text(form, "visit_address"),
            "region": _text(form, "visit_region"),
            "phone": _text(form, "visit_phone"),
            "website": links["visit_website"],
            "hours": _text(form, "visit_hours"),
            "credential": _text(form, "visit_credential"),
            "booking_risk": _text(form, "visit_booking_risk"),
            "lat": lat,
            "lon": lon,
        } if has_visit else None,
        "other_prices": [],
    }
    return wine


def add_wine(form: dict[str, Any]) -> dict[str, Any]:
    """File a new wine and write the catalogue. Returns the wine as stored."""
    data = json.loads(json.dumps(load_data()))     # a copy: nothing is mutated on failure
    catalogue = data["wines"]
    wine = build_wine(form, taken={w["slug"] for w in catalogue})

    catalogue.append(wine)
    # Cheapest first and numbered from one, which is how the file arrived and what the
    # pages say out loud ("No. 4 of 17"). Sorted on price alone and nothing else: three
    # pairs of wines share a price, and Python's stable sort leaves those in the order
    # the file already had them rather than shuffling six records to insert one.
    catalogue.sort(key=lambda w: (w["price_eur"] is None, w["price_eur"] or 0))
    for position, entry in enumerate(catalogue, start=1):
        entry["id"] = position

    save_data(data)
    return next(w for w in wines() if w["slug"] == wine["slug"])
