"""Draw a champagne bottle for each wine, instead of using a photograph.

This is a rights decision before it is a design one. The workbook's Images sheet opens
with "YOU CANNOT JUST COPY THESE IMAGES ONTO YOUR SITE" and explains why: retailer and
producer bottle photos belong to whoever shot them, and hotlinking them additionally
invites the host to block the request or change the path and leave a broken image on a
live page. Of the sixteen wines exactly one has a verified image URL. So the site draws
its own bottles - no permissions to chase, nothing to break, and a consistent look
across the range that sixteen scraped photos would never have had.

Each bottle is deterministic: the same wine always renders identically, because the
capsule colour is chosen by hashing the producer's name rather than by counter. The
glass is the dark green of real champagne; what varies is the foil capsule and the
label accent, keyed to the style of the wine, so a blanc de blancs and a blanc de noirs
are told apart at a glance in the grid.

The workbook's own advice for the real thing is on the detail page: ask the grower, or
shoot your own on the buying trip.
"""
from __future__ import annotations

import hashlib
import html
import re

# Foil colours a champagne house might plausibly use. Chosen to stay legible against
# both the light and dark page backgrounds.
CAPSULES: tuple[tuple[str, str], ...] = (
    ("#c9a227", "#8c6f14"),  # gold
    ("#7d2233", "#4e1420"),  # burgundy
    ("#1f3a5f", "#12233a"),  # navy
    ("#2f5d3f", "#1b3826"),  # forest
    ("#b4622d", "#78401d"),  # copper
    ("#4a4a52", "#2c2c31"),  # slate
    ("#8a1f3d", "#571326"),  # crimson
    ("#3d3522", "#241f14"),  # bronze
)

# The style of the wine drives the label accent, so the grid reads at a glance.
STYLE_ACCENTS: tuple[tuple[str, str, str], ...] = (
    ("blanc de blancs", "#c8b568", "Blanc de Blancs"),
    ("blanc de noirs", "#a8553a", "Blanc de Noirs"),
    ("extra brut", "#6f8f7a", "Extra Brut"),
    ("rosé", "#c47b86", "Rosé"),
    ("brut", "#b09a4e", "Brut"),
)


def style_accent(style: str) -> tuple[str, str]:
    """(colour, short label) for a style string, first match wins."""
    lowered = (style or "").lower()
    for needle, colour, label in STYLE_ACCENTS:
        if needle in lowered:
            return colour, label
    return "#9a9484", "Champagne"


def capsule_for(name: str) -> tuple[str, str]:
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=4).digest()
    return CAPSULES[digest[0] % len(CAPSULES)]


def monogram(producer: str) -> str:
    """One or two initials for the label. A single-word producer keeps one letter
    rather than borrowing one from the cuvée, which would read as a different house."""
    words = [w for w in re.findall(r"[^\W\d_]+", producer, re.UNICODE) if len(w) > 1]
    if not words:
        return "C"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


def bottle_svg(
    producer: str,
    cuvee: str,
    style: str = "",
    classification: str = "",
    width: int = 120,
    height: int = 380,
    decorative: bool = True,
) -> str:
    """One bottle as inline SVG.

    `decorative=True` marks it aria-hidden: in the grid the wine's name sits next to it
    as real text, so announcing the drawing as well would just repeat it. The detail
    page passes False and gets a described image.
    """
    bright, dark = capsule_for(producer)
    accent, style_label = style_accent(f"{style} {cuvee}")
    initials = monogram(producer)
    # Unique per bottle: two of these render side by side in the grid, and duplicate
    # gradient ids would make every bottle adopt the first one's colours.
    uid = hashlib.blake2b(f"{producer}|{cuvee}".encode(), digest_size=5).hexdigest()
    tier = (classification or "").lower()
    cru = "GRAND CRU" if "grand cru" in tier else ("1ER CRU" if "premier cru" in tier or "1er cru" in tier else "")

    outline = (
        "M50,22 L70,22 L70,120 "
        "C70,150 108,160 108,215 L108,352 "
        "C108,366 100,372 88,372 L32,372 "
        "C20,372 12,366 12,352 L12,215 "
        "C12,160 50,150 50,120 Z"
    )
    label_text = html.escape(style_label)
    aria = "" if decorative else (
        f'<title>Illustration of a champagne bottle representing '
        f'{html.escape(producer)} {html.escape(cuvee)}</title>'
    )

    return f"""<svg class="bottle" viewBox="0 0 120 380" width="{width}" height="{height}"
     xmlns="http://www.w3.org/2000/svg" role="img"
     {'aria-hidden="true" focusable="false"' if decorative else 'aria-label="' + html.escape(f"{producer} {cuvee}") + '"'}>
  {aria}
  <defs>
    <linearGradient id="glass{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#0f2a1c"/>
      <stop offset="28%" stop-color="#2e5c40"/>
      <stop offset="52%" stop-color="#183f2a"/>
      <stop offset="100%" stop-color="#0b1f14"/>
    </linearGradient>
    <linearGradient id="foil{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{dark}"/>
      <stop offset="40%" stop-color="{bright}"/>
      <stop offset="100%" stop-color="{dark}"/>
    </linearGradient>
    <clipPath id="body{uid}"><path d="{outline}"/></clipPath>
  </defs>

  <path d="{outline}" fill="url(#glass{uid})"/>

  <!-- Foil capsule over neck and lip, clipped so it cannot spill past the glass. -->
  <g clip-path="url(#body{uid})">
    <rect x="44" y="18" width="32" height="86" fill="url(#foil{uid})"/>
    <rect x="44" y="26" width="32" height="4" fill="{dark}" opacity=".55"/>
    <rect x="44" y="96" width="32" height="8" fill="{dark}" opacity=".45"/>
  </g>

  <!-- A single soft highlight reads as glass without looking like a gloss filter. -->
  <path d="{outline}" fill="none" stroke="rgba(255,255,255,.16)" stroke-width="1.5"/>
  <rect x="26" y="205" width="9" height="140" rx="4.5" fill="rgba(255,255,255,.13)"
        clip-path="url(#body{uid})"/>

  <!-- Label -->
  <rect x="20" y="232" width="80" height="86" rx="3" fill="#f4efe3"/>
  <rect x="20" y="232" width="80" height="86" rx="3" fill="none" stroke="rgba(0,0,0,.16)"/>
  <rect x="20" y="232" width="80" height="5" fill="{accent}"/>
  <text x="60" y="274" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif"
        font-size="26" font-weight="700" fill="#2b2b28" letter-spacing="1">{initials}</text>
  <text x="60" y="292" text-anchor="middle" font-family="Georgia, serif"
        font-size="7.5" fill="#6a655c" letter-spacing="1"
        textLength="{min(68, 4.6 * len(label_text))}" lengthAdjust="spacingAndGlyphs">{label_text.upper()}</text>
  {'<text x="60" y="308" text-anchor="middle" font-family="Georgia, serif" font-size="6.5" fill="' + accent + '" letter-spacing="1.1" textLength="' + str(min(52, 5.0 * len(cru))) + '" lengthAdjust="spacingAndGlyphs">' + cru + '</text>' if cru else ''}

  <!-- Neck band, the little foil collar most houses wear. -->
  <rect x="44" y="104" width="32" height="3" fill="{bright}" opacity=".8"
        clip-path="url(#body{uid})"/>
</svg>"""
