#!/usr/bin/env python3
"""Download the bottle photographs so the site serves its own copies.

    python scripts/fetch_images.py

Run this from a machine that can reach the retailers. It writes app/static/bottles/,
and app/main.py prefers those files over the remote URLs automatically - nothing else
needs changing.

Why bother, when the URLs work: they work until they don't. The workbook puts it
plainly - "the host can block it or change the path and your live product page shows a
broken image". A hotlinked page also asks the retailer's server for a favour on every
view, which is the sort of thing that gets a referrer blocked.

Downloading is not permission. These photographs belong to the retailer or the
producer. The workbook's route is: download them for your own work, then ask each
grower for written permission, or shoot your own bottles on the buying trip.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "champagnes.json"
OUT = REPO / "app" / "static" / "bottles"

# Some hosts refuse a bare urllib user agent outright.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChampagneUnderdogs/1.0; +https://github.com/marcomaggiotti/champagne_underdog_service)",
    "Accept": "image/avif,image/webp,image/jpeg,image/png,*/*",
}
SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
SPACING_SECONDS = 1.0  # one request per second; these are small shops


def download(url: str, slug: str) -> tuple[bool, str]:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
            body = response.read()
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (OSError, ValueError) as exc:
        return False, str(exc)

    if not content_type.startswith("image/"):
        # A shop that has removed a product often answers with an HTML page rather than
        # a 404, and saving that as a .jpg produces a broken image nobody notices.
        return False, f"not an image ({content_type or 'no content type'})"
    if len(body) < 1024:
        return False, f"suspiciously small ({len(body)} bytes)"

    OUT.mkdir(parents=True, exist_ok=True)
    for existing in OUT.glob(f"{slug}.*"):
        existing.unlink()
    target = OUT / f"{slug}{SUFFIXES.get(content_type, '.jpg')}"
    target.write_bytes(body)
    return True, f"{len(body) // 1024} KB -> {target.name}"


def main() -> None:
    if not DATA.exists():
        sys.exit(f"{DATA} is missing. Run scripts/import_xlsx.py first.")
    wines = json.loads(DATA.read_text(encoding="utf-8"))["wines"]

    saved = skipped = failed = 0
    for wine in wines:
        image = wine.get("image") or {}
        # Prefer the large variant: it is the one worth storing, and the site scales it.
        url = image.get("hires") or image.get("url")
        if not url:
            print(f"  --  {wine['producer']}: no image URL in the workbook")
            skipped += 1
            continue
        time.sleep(SPACING_SECONDS)
        ok, detail = download(url, wine["slug"])
        print(f"  {'OK' if ok else 'xx'}  {wine['producer']}: {detail}")
        saved += ok
        failed += not ok

    print(f"\n{saved} saved, {skipped} had no URL, {failed} failed -> {OUT.relative_to(REPO)}")
    if failed:
        print("Open the failures' product pages and copy the image address by hand.")
    if saved:
        print("Commit app/static/bottles/ and the site will serve these instead of hotlinking.")


if __name__ == "__main__":
    main()
