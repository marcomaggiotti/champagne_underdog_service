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
