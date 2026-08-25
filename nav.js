/* Mobile nav toggle, loaded by every page.

   The nav markup is identical on all 12 pages and the link row is plain HTML, so
   with this script absent the desktop nav still works exactly as before — only
   the sub-680px dropdown depends on it.

   Markup contract: a <nav> containing button.nav-toggle and div.nav-links.
   The .open class on each is what style.css keys the dropdown off. */
(function () {
  var nav = document.querySelector('nav');
  if (!nav) return;
  var btn   = nav.querySelector('.nav-toggle');
  var links = nav.querySelector('.nav-links');
  if (!btn || !links) return;

  function setOpen(open) {
    links.classList.toggle('open', open);
    btn.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  btn.addEventListener('click', function () {
    setOpen(!links.classList.contains('open'));
  });

  // Close after a tap on any link. Most of these are same-page fragments, which
  // don't reload, so without this the panel would stay open over the target.
  links.addEventListener('click', function (e) {
    if (e.target.closest('a')) setOpen(false);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && links.classList.contains('open')) {
      setOpen(false);
      btn.focus();
    }
  });
})();

/* Ctrl-click (or Cmd-click) the footer logo to reach the license admin.
 *
 * Hidden, not secret. This file is public, so anyone reading it learns the path, and that
 * is fine: the admin page is gated by Supabase Auth plus row level security, and signed
 * out the API returns nothing. The point is only to keep an internal tool out of the way
 * of visitors, without a link in the nav for them to wonder about.
 *
 * Delegated from document, so it works on all 12 pages regardless of footer markup, and
 * on the plain <img> logo which is not a link.
 */
(function () {
  document.addEventListener('click', function (e) {
    if (!e.ctrlKey && !e.metaKey) return;
    if (!e.target.closest('.footer-logo')) return;
    e.preventDefault();
    window.location.href = 'license-admin.html';
  });
})();
