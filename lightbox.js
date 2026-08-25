/* Click any content image to see it at full size.
 *
 * Opt-in by selector rather than grabbing every <img>, so nav and footer logos, app
 * tile icons and row icons stay unclickable. Images sitting inside a link are skipped
 * too: there the click already means "go to that page".
 *
 * Shared by all 12 pages. No dependencies.
 */
(function () {
  var SELECTOR = 'img.rd-elk, img.rt-phone, .rt-car-slide img, video.rd-elk';
  var overlay, imgEl, vidEl, capEl, closeBtn, lastFocus;

  function build() {
    overlay = document.createElement('div');
    overlay.className = 'lb-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Image preview');
    overlay.hidden = true;
    overlay.innerHTML =
      '<button class="lb-close" type="button" aria-label="Close preview">&times;</button>' +
      '<figure class="lb-figure">' +
        '<img class="lb-img" alt="">' +
        '<video class="lb-vid" controls loop muted playsinline></video>' +
        '<figcaption class="lb-cap"></figcaption>' +
      '</figure>';
    document.body.appendChild(overlay);
    imgEl = overlay.querySelector('.lb-img');
    vidEl = overlay.querySelector('.lb-vid');
    capEl = overlay.querySelector('.lb-cap');
    closeBtn = overlay.querySelector('.lb-close');

    // Backdrop and close button dismiss; clicking the picture itself does not, so a
    // stray click while reading a screenshot does not throw you out.
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay || e.target === capEl || closeBtn.contains(e.target)) close();
    });
  }

  function open(img) {
    if (!overlay) build();
    lastFocus = document.activeElement;

    // A page video opens as a video, with controls so it can be scrubbed.
    var isVideo = img.tagName === 'VIDEO';
    imgEl.hidden = isVideo;
    vidEl.hidden = !isVideo;
    if (isVideo) {
      vidEl.src = img.currentSrc || img.src;
      vidEl.play().catch(function () {});
    } else {
      imgEl.src = img.currentSrc || img.src;
      imgEl.alt = img.alt || '';
    }

    // Prefer the figure's own caption; fall back to alt text.
    var fig = img.closest('figure');
    var cap = fig ? fig.querySelector('figcaption') : null;
    var text = cap ? cap.textContent.trim() : (img.alt || img.getAttribute('aria-label') || '');
    capEl.textContent = text;
    capEl.hidden = !text;

    overlay.hidden = false;
    document.documentElement.classList.add('lb-open');
    closeBtn.focus();
  }

  function close() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.documentElement.classList.remove('lb-open');
    imgEl.removeAttribute('src');
    vidEl.pause();
    vidEl.removeAttribute('src');
    vidEl.load();
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' || e.key === 'Esc') close();
    // Keep tabbing inside the dialog while it is open.
    if (e.key === 'Tab' && overlay && !overlay.hidden) {
      e.preventDefault();
      closeBtn.focus();
    }
  });

  function init() {
    var imgs = document.querySelectorAll(SELECTOR);
    Array.prototype.forEach.call(imgs, function (img) {
      if (img.closest('a')) return;
      img.classList.add('lb-zoom');
      img.tabIndex = 0;
      img.setAttribute('role', 'button');
      var label = img.alt || img.getAttribute('aria-label') || '';
      img.setAttribute('aria-label', (label ? label + '. ' : '') + 'View full size');
      img.addEventListener('click', function () { open(img); });
      img.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(img); }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
