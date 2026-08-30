"""How a credential string becomes a tier, a rank and a badge.

This lived in scripts/import_xlsx.py, which was fine while the workbook was the only
way a wine could arrive. It is not any more: /admin adds one from a form, and a wine
added there has to be tiered and ranked by exactly the rules the workbook's own legend
states - otherwise the same credential would sort one way when imported and another way
when typed in, and the gallery's ordering would quietly stop meaning anything.

So the judgement lives here, once, and both paths call it.
"""
from __future__ import annotations

import re
import unicodedata

# A number attached to "stars", "pts" or "points" is a real rating. A bare year in
# "Guide Hachette 2026 (listed)" is not, which is the whole distinction the legend draws.
VERIFIED = re.compile(r"\b\d+\s*(?:stars?|pts|points)\b|coup de c", re.IGNORECASE)

#: Named by the guide but with the star count unconfirmed: ranked above the wines with
#: nothing, below every wine whose rating was actually pinned down.
LISTED_RANK = 0.25


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


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
    return "verified" if VERIFIED.search(professional) else "listed"


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


def derive(professional: str) -> dict:
    """Every rating field a wine record carries, from the one credential string."""
    professional = professional.strip()
    tier = score_tier(professional)
    parts = rating_parts(professional)
    return {
        "professional_score": professional,
        "score_tier": tier,
        "headline_score": headline_score(professional, tier, parts),
        "stars": parts["stars"],
        "points": parts["points"],
        "coup_de_coeur": parts["coup_de_coeur"],
        "rating_rank": LISTED_RANK if tier == "listed" else rating_rank(parts),
    }
