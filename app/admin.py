"""Adding a wine to the catalogue, from a browser, behind a login.

Everything else on this site is read-only and public. This is neither, so the two
decisions worth stating are here rather than buried in the handlers:

**The login is HTTP Basic.** It carries no session, sets no cookie and needs no secret
key to sign one, which for a single-operator admin page is the whole of the argument.
The credentials default to the pair this was asked for and are overridable by
environment - ADMIN_USER and ADMIN_PASSWORD - so a deployment is not stuck with a
password that is written down in a public repository. Set them on Render.

**A rating cannot be asserted, only evidenced.** The form has no "tier" control. You
type the credential as it is written - "2 stars, Guide Hachette 2026" - and the tier,
the rank and the badge are read off it by app/ratings.py, the same code the workbook
importer uses. That is deliberate: the site's central editorial promise is that a gold
badge means a rating somebody could verify, and a form that let an operator tick
"verified" would be a way to break that promise by hand.
"""
from __future__ import annotations

import os
import secrets
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .catalogue import ValidationError, add_wine, find, wines

#: The browser's own login box. A realm string, so the prompt says what it is for.
security = HTTPBasic(realm="Champagne Underdogs admin")

ADMIN_USER = os.environ.get("ADMIN_USER") or "admin"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "maorvelous"

UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Wrong username or password.",
    # Without this the browser has no way to ask again, and the operator is simply
    # locked out by a typo.
    headers={"WWW-Authenticate": 'Basic realm="Champagne Underdogs admin"'},
)


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Both halves are compared in constant time, and both are always compared.

    Returning early on a wrong username leaks which half was wrong through the clock.
    """
    user_ok = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    password_ok = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and password_ok):
        raise UNAUTHORISED
    return credentials.username


def same_origin(request: Request) -> None:
    """Refuse a form posted from somewhere else.

    Basic credentials are cached by the browser and attached to cross-site requests too,
    so without this a page on another domain could submit this form on a logged-in
    operator's behalf. Origin is sent on every browser POST; a client that sends none at
    all (curl, a test) is not a browser being used against its owner, and is let through.
    """
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail="Cross-site form submission refused.")


#: Blank strings rather than an empty dict: the template reads every field back out to
#: re-fill the form, and a missing key would render "None" in the input.
FIELDS = (
    "producer", "cuvee", "price_eur", "village", "classification", "style",
    "professional_score", "medals", "retailer_rating", "description",
    "verification_note", "product_url", "image_url", "image_status",
    "visit_name", "visit_address", "visit_region", "visit_phone", "visit_website",
    "visit_hours", "visit_credential", "visit_booking_risk", "visit_lat", "visit_lon",
)
BLANK = {field: "" for field in FIELDS}


def page(request: Request, templates, status_code: int = 200, **context: Any):
    return templates.TemplateResponse(request, "admin.html", {
        # No age gate here: the password is a stronger statement than the checkbox, and
        # the gate never lifts without script - which would make this page unusable
        # rather than merely gated. See base.html.
        "gated": False,
        "values": BLANK,
        "errors": {},
        "added": None,
        "catalogue": sorted(wines(), key=lambda w: w["id"]),
        **context,
    }, status_code=status_code)


def build(templates):
    """The routes, wired to the app's Jinja environment.

    Passed in rather than imported: main.py owns the environment - the bottle drawing,
    the price filter - and a second one here would render these pages without them.
    """
    router = APIRouter()

    @router.get("/admin", response_class=HTMLResponse)
    def new_champagne(request: Request, added: str = "", _: str = Depends(require_admin)):
        return page(request, templates, added=find(added) if added else None)

    @router.post("/admin", response_class=HTMLResponse)
    async def create_champagne(request: Request, _: str = Depends(require_admin)):
        same_origin(request)
        submitted = dict(await request.form())
        try:
            wine = add_wine(submitted)
        except ValidationError as invalid:
            # Back to the form with everything still in it. Losing a filled-in form to a
            # mistyped price is the fastest way to make an admin page go unused.
            return page(
                request, templates,
                values={**BLANK, **{k: str(v) for k, v in submitted.items() if k in BLANK}},
                errors=invalid.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        # Redirect rather than render, so a refresh does not file the wine twice.
        return RedirectResponse(f"/admin?added={wine['slug']}", status_code=status.HTTP_303_SEE_OTHER)

    return router
