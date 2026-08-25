"""The service, end to end through the HTTP layer.

The rules being protected here are editorial as much as technical. The workbook says of
the wines with no professional rating: "Do not imply one." Two thirds of the list is in
that position, so the tiering is the thing most worth a test - a refactor that collapsed
the three tiers into one score would be a factual regression, not a cosmetic one.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.bottles import bottle_svg, monogram, style_accent
from app.main import app, load_data, price_label

client = TestClient(app)


@pytest.fixture(scope="module")
def catalogue() -> list[dict]:
    return load_data()["wines"]


# --- the data --------------------------------------------------------------------

def test_the_catalogue_loaded(catalogue):
    assert len(catalogue) == 16
    assert all(w["slug"] and w["producer"] and w["cuvee"] for w in catalogue)


def test_slugs_are_unique(catalogue):
    """Two wines share a producer - Olivier Rousseaux has two cuvées - so a slug built
    from the producer alone would collide and hide one of them."""
    slugs = [w["slug"] for w in catalogue]
    assert len(slugs) == len(set(slugs))


def test_wines_are_sorted_cheapest_first(catalogue):
    prices = [w["price_eur"] for w in catalogue]
    assert prices == sorted(prices)


# --- the rating tiers ------------------------------------------------------------

def test_only_evidenced_ratings_are_marked_verified(catalogue):
    """A star count or a point score is a rating; a bare listing is not."""
    for wine in catalogue:
        if wine["score_tier"] == "verified":
            assert re.search(r"\d+\s*(stars?|pts|points)|coup de c",
                             wine["professional_score"], re.IGNORECASE), wine["producer"]


def test_an_unrated_wine_carries_no_score(catalogue):
    for wine in catalogue:
        if wine["score_tier"] == "none":
            assert not wine["professional_score"]
            assert not wine["headline_score"]


def test_the_three_tiers_are_all_present(catalogue):
    tiers = {w["score_tier"] for w in catalogue}
    assert tiers == {"verified", "listed", "none"}


def test_a_retailer_rating_is_never_a_professional_score(catalogue):
    """The workbook: "NOT a professional score. Keep it visually separate on the site."
    A wine rated only by customers must not be promoted into the verified tier."""
    for wine in catalogue:
        if wine["retailer_rating"] and not wine["professional_score"]:
            assert wine["score_tier"] == "none"


def test_the_unrated_page_does_not_imply_a_rating():
    body = client.get("/champagne/pescheux-reserve").text
    assert "No professional rating found" in body
    # Its 5.0 customer rating is on the page, but framed as what it is.
    assert "not a professional score" in body


# --- pages -------------------------------------------------------------------------

def test_health_reports_the_catalogue():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["wines"] == 16


def test_the_gallery_shows_every_wine(catalogue):
    body = client.get("/").text
    for wine in catalogue:
        assert f'/champagne/{wine["slug"]}' in body
        assert wine["producer"] in body


def test_the_gallery_is_gated_before_anything_else():
    """The gate ships in the HTML and the content ships hidden. If the gate were added
    by script the wines would flash first, and with scripting off never be gated."""
    body = client.get("/").text
    assert body.index('id="age-gate"') < body.index('id="site"')
    assert re.search(r'<div id="site" class="site" hidden>', body)
    assert "Are you 18 or over?" in body


def test_the_gate_says_the_site_does_not_sell():
    body = client.get("/").text
    assert "does not sell anything" in body
    assert "showcase only" in body.lower()


def test_a_detail_page_carries_the_whole_record():
    body = client.get("/champagne/jacques-chaput-brut-tradition").text
    for expected in [
        "Jacques Chaput", "Brut Tradition", "€26.50",
        "Coup de C",                       # its credential
        "Concours Mondial de Bruxelles",   # its medal
        "Arrentières",                     # where it is made
        "What was and was not verified",   # the honesty note
        "1 Rue Blanche",                   # visiting details
        "Plus de Bulles",                  # a price found elsewhere
    ]:
        assert expected in body, expected


def test_an_unknown_wine_returns_a_helpful_404():
    response = client.get("/champagne/chateau-nonexistent", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert "No such bottle" in response.text


def test_the_json_api_matches_the_file():
    assert client.get("/api/champagnes").json() == load_data()


def test_no_page_claims_to_sell_anything():
    """A showcase that grew a "Buy" button would be a different site with different
    obligations. Nothing in the templates should suggest a transaction."""
    pages = [client.get("/").text, client.get("/champagne/pescheux-reserve").text]
    for body in pages:
        lowered = body.lower()
        for forbidden in ["add to cart", "add to basket", "buy now", "checkout"]:
            assert forbidden not in lowered


# --- prices ------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (22.0, "€22"), (22.9, "€22.90"), (26.5, "€26.50"), (35.9, "€35.90"), (None, "—"),
])
def test_prices_keep_their_cents(value, expected):
    """€26.50 rendered as "€26.5" reads as a truncated number rather than a price."""
    assert price_label(value) == expected


# --- bottles -----------------------------------------------------------------------

def test_a_bottle_is_the_same_every_time():
    first = bottle_svg("Cyril Banchet", "Blanc de Blancs Grand Cru", "Blanc de Blancs", "Grand Cru")
    assert first == bottle_svg("Cyril Banchet", "Blanc de Blancs Grand Cru", "Blanc de Blancs", "Grand Cru")


def test_two_bottles_do_not_share_gradient_ids(catalogue):
    """Sixteen render on one page; duplicate ids would make them all adopt the first
    bottle's colours."""
    ids = set()
    for wine in catalogue:
        svg = bottle_svg(wine["producer"], wine["cuvee"], wine["style"], wine["classification"])
        found = set(re.findall(r'id="glass([0-9a-f]+)"', svg))
        assert not (found & ids), wine["producer"]
        ids |= found


def test_the_style_can_come_from_the_cuvee():
    """André Chemin's style column reads "100% Pinot Noir, 3 g/L"; only the cuvée says
    blanc de noirs, and the label has to pick it up from there."""
    _, label = style_accent("100% Pinot Noir, 3 g/L, 12.5% abv Tradition 1er Cru (Blanc de Noirs)")
    assert label == "Blanc de Noirs"


def test_a_single_word_producer_keeps_one_initial():
    assert monogram("Sonnette") == "S"
    assert monogram("Laëtitia et Olivier Marteaux") == "LM"


def test_producer_names_are_escaped_into_the_svg():
    svg = bottle_svg('Ma<script>alert(1)</script>', "Brut", decorative=False)
    assert "<script>" not in svg


# --- ordering ----------------------------------------------------------------------

def test_the_gallery_leads_with_the_best_credential():
    """The default order is by professional rating, strongest first."""
    body = client.get("/").text
    positions = {slug: body.index(f'/champagne/{slug}') for slug in [
        "jacques-chaput-brut-tradition",       # 3 stars (1001 Dégustations) + Coup de Cœur
        "claude-baron-cuvee-pierre-de-lune-blanc-de-blancs",  # 3 stars
        "besserat-de-bellefon-brut-bleu",      # 2 stars
        "pescheux-reserve",                    # nothing
    ]}
    order = sorted(positions, key=positions.get)
    assert order == [
        "jacques-chaput-brut-tradition",
        "claude-baron-cuvee-pierre-de-lune-blanc-de-blancs",
        "besserat-de-bellefon-brut-bleu",
        "pescheux-reserve",
    ]


def test_every_rated_wine_outranks_every_unrated_one(catalogue):
    from app.main import by_rating

    ordered = sorted(catalogue, key=by_rating)
    tiers = [w["score_tier"] for w in ordered]
    assert tiers.index("none") > max(i for i, t in enumerate(tiers) if t == "verified")
    # A guide listing is weak evidence, but it is more than none.
    assert tiers.index("none") > max(i for i, t in enumerate(tiers) if t == "listed")


def test_price_order_is_still_available():
    body = client.get("/?sort=price").text
    cheapest = body.index("/champagne/sonnette-brut-tradition")          # €22
    dearest = body.index("/champagne/besserat-de-bellefon-brut-bleu")    # €34.70
    assert cheapest < dearest


def test_an_unknown_sort_falls_back_rather_than_erroring():
    assert client.get("/?sort=nonsense").status_code == 200


def test_ties_are_broken_by_points_then_price(catalogue):
    """Three wines hold three stars; the order between them should be stable and
    explicable rather than whatever the workbook happened to list."""
    from app.main import by_rating

    three_star = [w for w in sorted(catalogue, key=by_rating) if w["rating_rank"] == 3.0]
    assert [w["producer"] for w in three_star] == ["Christian Naudé", "Sonnette", "Claude Baron"]


# --- ratings, after the workbook revision -------------------------------------------

def test_the_headline_quotes_the_best_point_score(catalogue):
    """André Chemin reads "94 pts (critic aggregate); 97 pts Decanter". Quoting the
    first number found understated it."""
    chemin = next(w for w in catalogue if w["producer"] == "André Chemin")
    assert chemin["points"] == 97
    assert chemin["headline_score"] == "97 pts (Decanter)"


def test_the_badge_never_credits_hachette_with_another_guide_s_stars(catalogue):
    """Jacques Chaput has two Hachette stars and three from 1001 Dégustations. The
    badge names Hachette, so it must show two."""
    chaput = next(w for w in catalogue if w["producer"] == "Jacques Chaput")
    assert chaput["stars"] == 3                  # the best any guide gave, used for ranking
    assert chaput["headline_score"].startswith("2★")   # what Hachette itself gave
    assert chaput["coup_de_coeur"]


def test_the_upgraded_ratings_came_through(catalogue):
    """Two wines moved from unconfirmed to three stars in this workbook revision."""
    for producer in ("Sonnette", "Christian Naudé"):
        wine = next(w for w in catalogue if w["producer"] == producer)
        assert wine["score_tier"] == "verified" and wine["stars"] == 3


# --- photographs ---------------------------------------------------------------------

def test_almost_every_wine_has_a_photograph(catalogue):
    with_photo = [w for w in catalogue if w["image"].get("url")]
    assert len(with_photo) == 15
    missing = [w["producer"] for w in catalogue if not w["image"].get("url")]
    assert missing == ["Besserat de Bellefon"]


def test_two_wines_by_one_producer_get_their_own_photographs(catalogue):
    """Matching on producer alone gave both Olivier Rousseaux cuvées the same bottle."""
    rousseaux = [w for w in catalogue if w["producer"] == "Olivier Rousseaux"]
    assert len(rousseaux) == 2
    urls = {w["image"]["url"] for w in rousseaux}
    assert len(urls) == 2
    tradition = next(w for w in rousseaux if "Tradition" in w["cuvee"])
    assert "tradition" in tradition["image"]["url"]


def test_the_gallery_renders_the_photographs():
    body = client.get("/").text
    assert body.count('class="photo"') == 15


def test_a_drawn_bottle_is_always_behind_the_photograph():
    """A hotlink can break at any time; the page must not be left with a hole."""
    body = client.get("/").text
    assert body.count('class="drawn"') == 16
    assert "onerror=" in body


def test_the_wine_without_a_photograph_still_shows_a_bottle():
    body = client.get("/champagne/besserat-de-bellefon-brut-bleu").text
    assert 'class="photo"' not in body
    assert "svg" in body
    assert "No photograph was found" in body


def test_a_downloaded_file_wins_over_the_retailer_url(tmp_path, monkeypatch):
    """Once scripts/fetch_images.py has run, the site must stop hotlinking."""
    from app import main

    wine = next(w for w in load_data()["wines"] if w["image"].get("url"))
    monkeypatch.setattr(main, "PHOTO_DIR", tmp_path)
    assert main.photo_for(wine).startswith("http")
    (tmp_path / f"{wine['slug']}.jpg").write_bytes(b"x")
    assert main.photo_for(wine) == f"/static/bottles/{wine['slug']}.jpg"


def test_the_detail_page_says_whose_photograph_it_is():
    body = client.get("/champagne/gaudriller-extra-brut-grand-cru").text
    flat = " ".join(body.split())  # the template wraps; the wording is what matters
    assert "champagne-terroir.fr" in flat
    assert "belongs to the retailer or the producer, not to this site" in flat
    assert "permission is sought" in flat
