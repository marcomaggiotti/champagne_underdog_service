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


# --- the map -----------------------------------------------------------------------

def test_the_houses_are_one_per_address_not_one_per_wine(catalogue):
    """Three wines on this list are made at Olivier Rousseaux's cellar in Verzenay.
    Mapped wine-by-wine that is three markers on one roof, two of them unreachable."""
    from app.winehouses import winehouses

    houses = winehouses(catalogue)
    addresses = [h["address"] for h in houses]
    assert len(addresses) == len(set(addresses))

    verzenay = next(h for h in houses if "Verzenay" in h["address"])
    assert len(verzenay["wines"]) == 3


def test_a_house_with_no_coordinates_is_not_mapped():
    """A marker at (0, 0) is in the Gulf of Guinea. Better no pin than a wrong one."""
    from app.winehouses import winehouses

    assert winehouses([
        {"slug": "a", "producer": "A", "cuvee": "Brut", "price_eur": 1,
         "headline_score": "", "score_tier": "none",
         "visit": {"name": "A", "address": "somewhere", "lat": None, "lon": None}},
        {"slug": "b", "producer": "B", "cuvee": "Brut", "price_eur": 1,
         "headline_score": "", "score_tier": "none", "visit": None},
    ]) == []


def test_every_mapped_house_carries_its_wines(catalogue):
    from app.winehouses import winehouses

    houses = winehouses(catalogue)
    assert houses, "the workbook's itinerary sheet should put nine houses on the map"
    mapped = sum(len(h["wines"]) for h in houses)
    assert mapped == sum(1 for w in catalogue if w["visit"] and w["visit"]["lat"] is not None)
    for house in houses:
        assert -90 <= house["lat"] <= 90 and -180 <= house["lon"] <= 180
        assert house["wines"]


def test_the_gallery_lists_the_houses_with_or_without_a_key():
    """The addresses are rendered by the server, so they survive a missing API key, a
    blocked script and scripting switched off entirely."""
    body = client.get("/").text
    assert "Where they are made" in body
    for expected in ["Champagne Jacques Chaput & Fils".replace("&", "&amp;"),
                     "1 Rue Blanche, 10200 Arrentières",
                     "www.google.com/maps/search/"]:
        assert expected in body, expected


def test_without_a_key_the_map_says_so_rather_than_drawing_a_grey_box(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "GOOGLE_MAPS_API_KEY", "")
    body = client.get("/").text
    assert "The map is switched off" in body
    assert 'id="map-data"' not in body and "/static/map.js" not in body


def test_with_a_key_the_map_and_its_pins_are_on_the_page(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "GOOGLE_MAPS_API_KEY", "test-key")
    body = client.get("/").text
    assert 'data-maps-key="test-key"' in body
    assert '<script src="/static/map.js"></script>' in body

    pins = json.loads(re.search(r'id="map-data">(.*?)</script>', body, re.S).group(1))
    assert len(pins) == 9
    # An ampersand in "Chaput & Fils" must not be able to close the script element.
    assert "</script>" not in body[body.index('id="map-data"'):body.index("</script>", body.index('id="map-data"'))]
    assert any(p["name"] == "Champagne Jacques Chaput & Fils" for p in pins)


def test_the_map_data_is_also_available_as_json():
    body = client.get("/api/winehouses").json()
    assert body["count"] == len(body["houses"]) == 9
    assert {"name", "address", "lat", "lon", "wines"} <= set(body["houses"][0])


# --- adding a wine -------------------------------------------------------------------
#
# Every test here writes, so every one of them writes to a copy. A test that appended to
# data/champagnes.json would pass once and then change the answer to every test above it.

from app import catalogue as store          # noqa: E402  - imported here, beside its tests

GOOD = {"producer": "Test Grower", "cuvee": "Brut Nature", "price_eur": "24.90"}
LOGIN = ("admin", "maorvelous")


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """The catalogue, on a copy nobody else can see."""
    copy = tmp_path / "champagnes.json"
    copy.write_text(store.DATA.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(store, "DATA", copy)
    store.load_data.cache_clear()
    yield copy
    store.load_data.cache_clear()


def stored(path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["wines"]


def test_the_admin_page_is_shut_without_a_login():
    response = client.get("/admin")
    assert response.status_code == 401
    # Without this header the browser cannot offer a login box, and nobody gets in at all.
    assert response.headers["www-authenticate"].startswith("Basic")


def test_the_wrong_password_does_not_open_it():
    assert client.get("/admin", auth=("admin", "not-the-password")).status_code == 401
    assert client.get("/admin", auth=("someone", "maorvelous")).status_code == 401


def test_the_right_login_opens_the_form():
    response = client.get("/admin", auth=LOGIN)
    assert response.status_code == 200
    assert '<form class="adminform" method="post" action="/admin">' in response.text
    assert 'name="producer"' in response.text and 'name="visit_lat"' in response.text


def test_a_wine_cannot_be_added_without_the_login(scratch):
    before = len(stored(scratch))
    assert client.post("/admin", data=GOOD).status_code == 401
    assert client.post("/admin", data=GOOD, auth=("admin", "wrong")).status_code == 401
    assert len(stored(scratch)) == before


def test_adding_a_wine_puts_it_on_the_site(scratch):
    response = client.post("/admin", data={
        **GOOD,
        "professional_score": "2 stars, Guide Hachette 2026",
        "visit_address": "1 Rue de la Vigne, 51200 Épernay",
        "visit_lat": "49.05", "visit_lon": "3.95",
    }, auth=LOGIN, follow_redirects=False)
    # A redirect, not a rendered page: a refresh must not file the wine a second time.
    assert response.status_code == 303
    assert response.headers["location"] == "/admin?added=test-grower-brut-nature"

    assert len(stored(scratch)) == 17
    assert client.get("/champagne/test-grower-brut-nature").status_code == 200
    body = client.get("/").text
    assert "/champagne/test-grower-brut-nature" in body
    assert "Seventeen Champagnes" in body        # the copy counts, it does not say sixteen
    assert client.get("/api/winehouses").json()["count"] == 10


def test_an_added_wine_is_tiered_by_its_evidence_not_by_assertion(scratch):
    """The form has no "tier" control on purpose. A gold badge is supposed to mean
    somebody verified a rating, so the credential text is the only thing that can earn
    one - and a form that could assert it would be a way to fake it by hand."""
    client.post("/admin", data={**GOOD, "professional_score": "Guide Hachette 2026 (listed)",
                                "score_tier": "verified", "rating_rank": "99"},
                auth=LOGIN)
    wine = next(w for w in stored(scratch) if w["slug"] == "test-grower-brut-nature")
    assert wine["score_tier"] == "listed"        # not what the request asked for
    assert wine["rating_rank"] == 0.25
    assert wine["headline_score"] == "Guide Hachette listed"


def test_an_added_wine_with_no_credential_claims_nothing(scratch):
    client.post("/admin", data=GOOD, auth=LOGIN)
    wine = next(w for w in stored(scratch) if w["slug"] == "test-grower-brut-nature")
    assert wine["score_tier"] == "none"
    assert wine["headline_score"] == "" and wine["professional_score"] == ""
    assert "No professional rating found" in client.get("/champagne/" + wine["slug"]).text


def test_the_file_keeps_its_order_and_its_numbering(scratch):
    """It is stored cheapest-first and numbered from one, and the pages say so out loud
    ("No. 4 of 17"). An insert has to hold both, not append and hope."""
    client.post("/admin", data={**GOOD, "price_eur": "23.50"}, auth=LOGIN)
    wines_now = stored(scratch)
    prices = [w["price_eur"] for w in wines_now]
    assert prices == sorted(prices)
    assert [w["id"] for w in wines_now] == list(range(1, len(wines_now) + 1))
    assert len({w["slug"] for w in wines_now}) == len(wines_now)


def test_wines_sharing_a_price_are_not_shuffled_to_insert_one(scratch):
    """Three pairs on this list share a price. Re-sorting on anything but the price
    would reorder six records - and renumber them - to file one."""
    before = [w["slug"] for w in stored(scratch)]
    client.post("/admin", data={**GOOD, "price_eur": "40"}, auth=LOGIN)
    after = [w["slug"] for w in stored(scratch) if w["slug"] != "test-grower-brut-nature"]
    assert after == before


def test_a_repeated_name_gets_its_own_page_rather_than_overwriting_one(scratch):
    for _ in range(2):
        client.post("/admin", data=GOOD, auth=LOGIN)
    slugs = [w["slug"] for w in stored(scratch) if w["producer"] == "Test Grower"]
    assert slugs == ["test-grower-brut-nature", "test-grower-brut-nature-2"]
    for slug in slugs:
        assert client.get(f"/champagne/{slug}").status_code == 200


def test_a_bad_form_saves_nothing_and_gives_the_typing_back(scratch):
    before = len(stored(scratch))
    response = client.post("/admin", data={
        "producer": "Half Finished", "cuvee": "", "price_eur": "about twenty",
    }, auth=LOGIN)
    assert response.status_code == 400
    assert len(stored(scratch)) == before
    assert "Nothing was saved" in response.text
    assert 'value="Half Finished"' in response.text      # the form comes back filled in


def test_half_a_coordinate_is_refused(scratch):
    """One half of a pair puts the pin in the sea rather than in Champagne."""
    response = client.post("/admin", data={**GOOD, "visit_lat": "49.05"}, auth=LOGIN)
    assert response.status_code == 400
    assert "the map needs both" in response.text
    assert len(stored(scratch)) == 16


def test_an_impossible_coordinate_is_refused(scratch):
    response = client.post("/admin", data={**GOOD, "visit_lat": "999", "visit_lon": "3.95"},
                           auth=LOGIN)
    assert response.status_code == 400
    assert len(stored(scratch)) == 16


@pytest.mark.parametrize("field", ["product_url", "image_url", "visit_website"])
def test_a_script_url_never_reaches_an_href(scratch, field):
    """Every URL on this form is rendered into a link or an <img src>. Escaping does not
    make `javascript:` safe there - it is a perfectly valid attribute value."""
    response = client.post("/admin", data={**GOOD, field: "javascript:alert(1)"}, auth=LOGIN)
    assert response.status_code == 400
    assert len(stored(scratch)) == 16


def test_a_form_posted_from_another_site_is_refused(scratch):
    """Browsers attach cached Basic credentials to cross-site requests too, so the login
    alone does not stop another page from submitting this form on the operator's behalf."""
    response = client.post("/admin", data=GOOD, auth=LOGIN,
                           headers={"origin": "https://not-this-site.example"})
    assert response.status_code == 403
    assert len(stored(scratch)) == 16


def test_the_catalogue_is_never_left_half_written(scratch, monkeypatch):
    """The file is written beside itself and moved into place. A crash mid-write must
    leave the old catalogue readable rather than a truncated one."""
    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store.os, "replace", explode)
    with pytest.raises(OSError):
        client.post("/admin", data=GOOD, auth=LOGIN)

    store.load_data.cache_clear()
    assert len(stored(scratch)) == 16
    assert client.get("/health").json()["wines"] == 16
    # And nothing was left lying about beside it.
    assert not list(scratch.parent.glob(".champagnes-*.json"))


def test_the_committed_catalogue_is_untouched_by_all_of_this():
    """The fixtures write to copies. If one ever did not, this is what would say so."""
    assert len(load_data()["wines"]) == 16


@pytest.mark.parametrize("value", ["nan", "inf", "1e400"])
def test_a_price_that_is_not_json_is_refused(scratch, value):
    """float("nan") is a number to Python and is not JSON. Written out it becomes the
    bare token NaN, and the catalogue stops being a file anyone else can read."""
    response = client.post("/admin", data={**GOOD, "price_eur": value}, auth=LOGIN)
    assert response.status_code == 400
    assert json.loads(scratch.read_text(encoding="utf-8"))      # still parses, strictly
    assert len(stored(scratch)) == 16


def test_the_written_catalogue_is_strict_json(scratch):
    """What is written has to survive a reader that is not Python's."""
    client.post("/admin", data={**GOOD, "description": 'He said "château" — 100% pinot'},
                auth=LOGIN)
    json.loads(scratch.read_text(encoding="utf-8"), parse_constant=_no_constants)
    wine = next(w for w in stored(scratch) if w["slug"] == "test-grower-brut-nature")
    assert wine["description"] == 'He said "château" — 100% pinot'


def _no_constants(name):
    raise AssertionError(f"{name} is not JSON")


def test_the_admin_page_is_behind_a_password_not_behind_the_age_gate():
    """The gate never lifts without script, which is the right way to fail for a public
    showcase and the wrong way to fail for the form it is edited with. A password says
    more about who is asking than a checkbox does."""
    body = client.get("/admin", auth=LOGIN).text
    assert 'id="age-gate"' not in body
    assert '<div id="site" class="site">' in body      # visible, not hidden
    # And the public page is still gated exactly as it was.
    assert '<div id="site" class="site" hidden>' in client.get("/").text


def test_the_importers_ratings_and_the_forms_ratings_are_the_same_ratings(catalogue):
    """app/ratings.py was lifted out of scripts/import_xlsx.py so that a wine typed into
    /admin is tiered by the same rules as one read from the workbook. Re-deriving every
    committed record from its credential string is what says the lift changed nothing."""
    from app.ratings import derive

    for wine in catalogue:
        again = derive(wine["professional_score"])
        for field in ("score_tier", "headline_score", "stars", "points",
                      "coup_de_coeur", "rating_rank"):
            assert again[field] == wine[field], f'{wine["producer"]}: {field}'
