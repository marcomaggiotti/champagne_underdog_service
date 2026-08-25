/* The growers, on a Google map.
 *
 * Three things this has to get right, none of them about maps:
 *
 * 1. The map is inside the age-gated part of the page, which ships hidden. A map
 *    initialised inside a hidden element measures zero and renders as a grey square
 *    that never recovers, so nothing here starts until the gate has lifted - the gate
 *    announces that with a 'site:revealed' event.
 * 2. Google's script is only fetched at that point too. A visitor who never confirms
 *    their age never loads it, which is both a billed request they should not cost and
 *    a third party they never asked for.
 * 3. Markers are built from a JSON block the server rendered, never from HTML strings.
 *    A producer called "Chaput & Fils" is a string, and it stays one.
 */
(function () {
  'use strict';

  var map = document.getElementById('map');
  var payload = document.getElementById('map-data');
  if (!map || !payload) return;

  var houses;
  try { houses = JSON.parse(payload.textContent); } catch (err) { houses = []; }
  if (!houses.length) return;

  function note(text) {
    map.innerHTML = '';
    var p = document.createElement('p');
    p.className = 'map-note';
    p.textContent = text;
    map.appendChild(p);
  }

  /* One house's info window: name, where it is, and which of its wines are on the
     list. Built as nodes rather than a string - see (3) above. */
  function card(house) {
    var box = document.createElement('div');
    box.className = 'pin';

    var title = document.createElement('strong');
    title.textContent = house.name;
    box.appendChild(title);

    ['region', 'address'].forEach(function (field) {
      if (!house[field]) return;
      var line = document.createElement('span');
      line.textContent = house[field];
      box.appendChild(line);
    });

    var list = document.createElement('ul');
    house.wines.forEach(function (wine) {
      var item = document.createElement('li');
      var link = document.createElement('a');
      link.href = '/champagne/' + encodeURIComponent(wine.slug);
      link.textContent = wine.cuvee || wine.producer;
      item.appendChild(link);
      list.appendChild(item);
    });
    box.appendChild(list);

    if (house.booking_risk) {
      var risk = document.createElement('em');
      risk.textContent = house.booking_risk;
      box.appendChild(risk);
    }
    return box;
  }

  function draw() {
    var bounds = new google.maps.LatLngBounds();
    var drawn = new google.maps.Map(map, {
      mapTypeControl: false,
      streetViewControl: false,
      // Champagne is small and the pins are close together; without this the fit below
      // zooms in far enough that neighbouring villages fall off the edges.
      maxZoom: 12
    });
    var open = new google.maps.InfoWindow();

    houses.forEach(function (house) {
      var at = { lat: house.lat, lng: house.lon };
      /* google.maps.Marker rather than AdvancedMarkerElement: the advanced one needs a
         cloud-configured Map ID, and this has to work with nothing but an API key. */
      var marker = new google.maps.Marker({ position: at, map: drawn, title: house.name });
      marker.addListener('click', function () {
        open.setContent(card(house));
        open.open({ map: drawn, anchor: marker });
      });
      bounds.extend(at);
    });

    drawn.fitBounds(bounds, 48);
  }

  function load() {
    var key = map.getAttribute('data-maps-key');
    if (!key) return;
    if (window.google && window.google.maps) { draw(); return; }

    window.__champagneMapReady = function () {
      delete window.__champagneMapReady;
      draw();
    };
    var script = document.createElement('script');
    script.src = 'https://maps.googleapis.com/maps/api/js?key=' + encodeURIComponent(key) +
                 '&callback=__champagneMapReady&loading=async';
    script.async = true;
    script.onerror = function () {
      note('The map could not be loaded. The addresses are listed below.');
    };
    document.head.appendChild(script);
  }

  var site = document.getElementById('site');
  if (site && site.hidden) {
    document.addEventListener('site:revealed', load, { once: true });
  } else {
    load();
  }
})();
