"""Champagne Underdogs - a showcase for sixteen grower Champagnes under €40.

A web service rather than a bundle of static files, because it is deployed on Render as
one: the pages are rendered from data/champagnes.json on request, so correcting a price
means editing the JSON and redeploying rather than regenerating a site.

The site sells nothing. There is no basket, no checkout and no price that can be acted
on - the prices are research figures, retrieved on a stated date, shown so the reader
can see what a bottle costs at the property. Every visitor confirms they are of legal
drinking age before any of it is shown.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .bottles import bottle_svg, style_accent

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "data" / "champagnes.json"

app = FastAPI(
    title="Champagne Underdogs",
    description="A showcase of sixteen grower Champagnes under €40. Not a shop.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@lru_cache(maxsize=1)
def load_data() -> dict[str, Any]:
    """Read the catalogue once per process.

    Cached because the file never changes while the service runs - a correction ships as
    a redeploy, which is a fresh process.
    """
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


def price_label(value: float | None) -> str:
    """€22 for a round price, €26.50 for anything else.

    Stripping trailing zeros unconditionally turned €26.50 into "€26.5", which reads as
    a truncated number rather than a price.
    """
    if value is None:
        return "—"
    return f"€{value:,.0f}" if float(value).is_integer() else f"€{value:,.2f}"


# Jinja needs these; registering them here keeps the templates free of imports.
templates.env.globals["bottle"] = lambda w, **kw: Markup(
    bottle_svg(w["producer"], w["cuvee"], w["style"], w["classification"], **kw)
)
templates.env.globals["accent_of"] = lambda w: style_accent(f"{w['style']} {w['cuvee']}")[0]
templates.env.filters["price"] = price_label


@app.get("/", response_class=HTMLResponse)
def gallery(request: Request):
    catalogue = wines()
    return templates.TemplateResponse(request, "index.html", {
        "wines": catalogue,
        "notes": load_data()["notes"],
        "cheapest": min((w["price_eur"] for w in catalogue if w["price_eur"]), default=None),
        "dearest": max((w["price_eur"] for w in catalogue if w["price_eur"]), default=None),
        "rated": sum(1 for w in catalogue if w["score_tier"] == "verified"),
    })


@app.get("/champagne/{slug}", response_class=HTMLResponse)
def detail(request: Request, slug: str):
    wine = find(slug)
    if wine is None:
        raise HTTPException(status_code=404, detail=f"No champagne with the name {slug!r}.")
    catalogue = wines()
    position = next(i for i, w in enumerate(catalogue) if w["slug"] == slug)
    return templates.TemplateResponse(request, "detail.html", {
        "wine": wine,
        # Previous/next by price, so the list can be walked in the order it is presented.
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
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


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
