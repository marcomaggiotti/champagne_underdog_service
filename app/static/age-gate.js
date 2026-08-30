/* The age gate.
 *
 * The gate markup ships with the page and this script removes it, rather than the other
 * way round. If it were injected by script, the wines would be visible for the moment
 * before it ran, and with scripting disabled they would stay visible for good. Done this
 * way, no script means the gate never lifts - which is the safe direction to fail in.
 *
 * The confirmation lives in this browser only. It is a declaration, not verification,
 * which is all an age gate of this kind ever is.
 */
(function () {
  'use strict';

  var KEY = 'champagne-underdogs:age-confirmed';
  var gate = document.getElementById('age-gate');
  var site = document.getElementById('site');
  if (!gate || !site) return;

  function reveal() {
    gate.remove();
    site.hidden = false;
    document.body.classList.remove('gated');
    // The map cannot measure itself inside a hidden element, so it waits for this
    // rather than for load. Anything else that needs a laid-out page can too.
    document.dispatchEvent(new CustomEvent('site:revealed'));
  }

  function remember() {
    // Private windows and blocked site data both throw here. Failing to remember the
    // answer is a minor annoyance; failing the whole page over it is not acceptable.
    try { localStorage.setItem(KEY, String(Date.now())); } catch (err) { /* ignore */ }
  }

  var confirmed = false;
  try { confirmed = localStorage.getItem(KEY) !== null; } catch (err) { confirmed = false; }

  if (confirmed) { reveal(); return; }

  document.body.classList.add('gated');

  document.getElementById('gate-yes').addEventListener('click', function () {
    remember();
    reveal();
  });

  document.getElementById('gate-no').addEventListener('click', function () {
    var refused = document.getElementById('gate-refused');
    refused.hidden = false;
    document.querySelector('.gate-actions').hidden = true;
    refused.setAttribute('tabindex', '-1');
    refused.focus();
  });

  // Keep focus inside the dialog: tabbing to page furniture behind an age gate is both
  // confusing and pointless, since none of it is reachable.
  gate.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = gate.querySelectorAll('button:not([hidden])');
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
