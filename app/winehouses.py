"""The growers' addresses, gathered into map pins.

The catalogue is a list of wines, and a wine carries the address of the house that made
it. A map wants the other shape: one pin per house, however many of its wines are on the
list. Three of the sixteen entries point at Olivier Rousseaux's cellar in Verzenay, so
mapping the list wine-by-wine would stack three markers on one roof and hide two of
them behind the third.

Grouping is by address, not by name: the addresses are exact strings from the workbook's
itinerary sheet, while the names are spelt inconsistently across its sheets ("Cyril" in
one, "Cyrill" in another), which is the same reason the importer matches on surnames.
"""
from __future__ import annotations

from typing import Any


def _key(visit: dict[str, Any]) -> str:
    return " ".join((visit.get("address") or visit.get("name") or "").lower().split())


def winehouses(catalogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per house that can be put on a map, in the catalogue's own order.

    A house with no coordinates is left out: a marker at (0, 0) is in the Gulf of
    Guinea, and a pin in the wrong place is worse than no pin at all.
    """
    houses: dict[str, dict[str, Any]] = {}
    for wine in catalogue:
        visit = wine.get("visit")
        if not visit or visit.get("lat") is None or visit.get("lon") is None:
            continue
        house = houses.setdefault(_key(visit), {
            "name": visit.get("name") or wine["producer"],
            "address": visit.get("address") or "",
            "region": visit.get("region") or "",
            "phone": visit.get("phone") or "",
            "website": visit.get("website") or "",
            "hours": visit.get("hours") or "",
            "booking_risk": visit.get("booking_risk") or "",
            "lat": visit["lat"],
            "lon": visit["lon"],
            "wines": [],
        })
        house["wines"].append({
            "slug": wine["slug"],
            "producer": wine["producer"],
            "cuvee": wine["cuvee"],
            "price_eur": wine["price_eur"],
            "headline_score": wine["headline_score"],
            "score_tier": wine["score_tier"],
        })
    return list(houses.values())
