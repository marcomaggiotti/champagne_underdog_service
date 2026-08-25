"""Champagne Underdogs - a showcase for grower Champagnes under €40.

A web service rather than a bundle of static files, because it is deployed on Render as
one: the pages are rendered from data/champagnes.json on request, so correcting a price
means editing the JSON and redeploying rather than regenerating a site. /admin adds to
that file directly, which is why nothing here counts the wines for you - the list
started at sixteen and the pages say however many there are now.

The site sells nothing. There is no basket, no checkout and no price that can be acted
on - the prices are research figures, retrieved on a stated date, shown so the reader
can see what a bottle costs at the property. Every visitor confirms they are of legal
drinking age before any of it is shown.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import admin
from .bottles import bottle_svg, style_accent
# Reading and writing the catalogue lives in one place now that /admin can write to it.
from .catalogue import find, load_data, wines
from .winehouses import winehouses

BASE = Path(__file__).resolve().parent

#: Google Maps refuses to draw a map without a key, so the gallery falls back to a
#: plain list of the houses when there is none. Set it on Render; see the README.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()

app = FastAPI(
    title="Champagne Underdogs",
    description="A showcase of sixteen grower Champagnes under €40. Not a shop.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


#: Where scripts/fetch_images.py puts downloaded photographs.
PHOTO_DIR = BASE / "static" / "bottles"


def photo_for(wine: dict[str, Any], hires: bool = False) -> str:
    """The bottle photograph to show, preferring our own copy.

    A downloaded file wins over the retailer's URL every time. Hotlinking works right up
    until the host blocks it or moves the path, and then the page has a hole in it -
    which is exactly what the workbook warns about. Run scripts/fetch_images.py and this
    starts serving local files with no other change.

    Returns "" when there is no photograph at all, and the drawn bottle stands in.
    """
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        local = PHOTO_DIR / f"{wine['slug']}{suffix}"
        if local.exists():
            return f"/static/bottles/{local.name}"
    image = wine.get("image") or {}
    if hires and image.get("hires"):
        return image["hires"]
    return image.get("url") or ""


def by_rating(wine: dict[str, Any]) -> tuple:
    """Best-credentialled first.

    Ties are broken by point score and then by price, so three three-star wines appear
    cheapest-last rather than in whatever order the workbook happened to list them.
    """
    return (-wine["rating_rank"], -(wine.get("points") or 0), wine["price_eur"] or 0)


def by_price(wine: dict[str, Any]) -> tuple:
    return (wine["price_eur"] or 0,)


SORTS = {"rating": by_rating, "price": by_price}


def price_label(value: float | None) -> str:
    """€22 for a round price, €26.50 for anything else.

    Stripping trailing zeros unconditionally turned €26.50 into "€26.5", which reads as
    a truncated number rather than a price.
    """
    if value is None:
        return "—"
    return f"€{value:,.0f}" if float(value).is_integer() else f"€{value:,.2f}"


#: Small numbers read better spelt out in the site's own voice, and the count is no
#: longer fixed at sixteen now that a wine can be added through /admin.
_NUMBER_WORDS = (
    "no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty",
)


def in_words(value: int) -> str:
    return _NUMBER_WORDS[value] if 0 <= value < len(_NUMBER_WORDS) else f"{value:,}"


def total_wines() -> int:
    """How many wines the site is showing. Zero if the catalogue cannot be read at all -
    every page's furniture asks for this, and none of them should 500 over a headline."""
    try:
        return len(wines())
    except RuntimeError:
        return 0


# Jinja needs these; registering them here keeps the templates free of imports.
templates.env.globals["bottle"] = lambda w, **kw: Markup(
    bottle_svg(w["producer"], w["cuvee"], w["style"], w["classification"], **kw)
)
templates.env.globals["accent_of"] = lambda w: style_accent(f"{w['style']} {w['cuvee']}")[0]
templates.env.globals["photo_for"] = photo_for
templates.env.globals["total_wines"] = total_wines
templates.env.filters["price"] = price_label
templates.env.filters["words"] = in_words


@app.get("/", response_class=HTMLResponse)
def gallery(
    request: Request,
    sort: str = Query(default="rating", description="'rating' (default) or 'price'"),
):
    sort = sort if sort in SORTS else "rating"
    catalogue = sorted(wines(), key=SORTS[sort])
    return templates.TemplateResponse(request, "index.html", {
        "wines": catalogue,
        "sort": sort,
        "notes": load_data()["notes"],
        "cheapest": min((w["price_eur"] for w in catalogue if w["price_eur"]), default=None),
        "dearest": max((w["price_eur"] for w in catalogue if w["price_eur"]), default=None),
        "rated": sum(1 for w in catalogue if w["score_tier"] == "verified"),
        # The map. Grouped by address, so the three wines from Verzenay share one pin
        # rather than stacking three markers on one roof.
        "houses": winehouses(catalogue),
        "maps_key": GOOGLE_MAPS_API_KEY,
    })


@app.get("/champagne/{slug}", response_class=HTMLResponse)
def detail(request: Request, slug: str):
    wine = find(slug)
    if wine is None:
        raise HTTPException(status_code=404, detail=f"No champagne with the name {slug!r}.")
    catalogue = sorted(wines(), key=by_rating)
    position = next(i for i, w in enumerate(catalogue) if w["slug"] == slug)
    return templates.TemplateResponse(request, "detail.html", {
        "wine": wine,
        # Previous/next in the gallery's own order, so the list can be walked as shown.
        "previous": catalogue[position - 1] if position > 0 else None,
        "next": catalogue[position + 1] if position + 1 < len(catalogue) else None,
    })


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    """A missing bottle should offer the way back, not a bare JSON error."""
    if exc.status_code == 404 and "text/html" in (request.headers.get("accept") or ""):
        return templates.TemplateResponse(
            request, "404.html", {"detail": exc.detail}, status_code=404,
        )
    # exc.headers carries WWW-Authenticate on a 401. Dropping it leaves the browser with
    # a bare "Unauthorized" and no way to offer the login box, which locks the operator
    # out of /admin entirely.
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                        headers=exc.headers)


@app.get("/health")
def health():
    """Render's health check. Reports the catalogue so a deploy with missing or empty
    data fails visibly here rather than serving an empty gallery."""
    try:
        catalogue = wines()
    except RuntimeError as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
    return {"status": "ok", "service": "champagne-underdogs", "wines": len(catalogue)}


@app.get("/api/champagnes")
def api_champagnes():
    """The catalogue as JSON - the same data the pages are rendered from."""
    return load_data()


@app.get("/api/winehouses")
def api_winehouses():
    """The map's pins: one per house, with whichever of its wines are on the list."""
    houses = winehouses(wines())
    return {"houses": houses, "count": len(houses)}


# Adding a wine, behind a login. Registered last so the public site is fully wired
# before anything that can write to it exists.
app.include_router(admin.build(templates))
