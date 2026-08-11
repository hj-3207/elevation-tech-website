/* Screenshot carousel, shared by rack-tracker.html and rack-scorer.html.
   Was duplicated inline in both pages; extracted so one fix reaches both.

   The track is a real horizontal scroll-snap scroller, so swipe and trackpad
   gestures work natively and keep working if this script never runs — the
   buttons, dots and counter are the progressive enhancement on top.

   Markup contract: a [data-carousel] root containing [data-car-track] with
   .rt-car-slide children, plus [data-car-dots], [data-car-count],
   [data-car-prev] and [data-car-next]. Styles live in style.css under rt-car-*. */
(function () {
  document.querySelectorAll('[data-carousel]').forEach(function (root) {
    var track  = root.querySelector('[data-car-track]');
    var slides = Array.prototype.slice.call(root.querySelectorAll('.rt-car-slide'));
    var dotBox = root.querySelector('[data-car-dots]');
    var count  = root.querySelector('[data-car-count]');
    var prev   = root.querySelector('[data-car-prev]');
    var next   = root.querySelector('[data-car-next]');
    if (!track || !slides.length) return;

    var current = 0;
    var reduce  = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var dots = slides.map(function (_, i) {
      var d = document.createElement('button');
      d.type = 'button';
      d.className = 'rt-car-dot';
      d.setAttribute('aria-label', 'Go to screenshot ' + (i + 1));
      d.addEventListener('click', function () { go(i); });
      dotBox.appendChild(d);
      return d;
    });

    function go(i) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      // scrollIntoView would also scroll the page vertically on some browsers,
      // so drive scrollLeft directly off the slide's offset within the track.
      track.scrollTo({ left: slides[i].offsetLeft - track.offsetLeft, behavior: reduce ? 'auto' : 'smooth' });
      paint(i);
    }

    function paint(i) {
      current = i;
      dots.forEach(function (d, n) {
        d.classList.toggle('active', n === i);
        d.setAttribute('aria-current', n === i ? 'true' : 'false');
      });
      count.textContent = (i + 1) + ' / ' + slides.length;
      prev.disabled = i === 0;
      next.disabled = i === slides.length - 1;
    }

    prev.addEventListener('click', function () { go(current - 1); });
    next.addEventListener('click', function () { go(current + 1); });

    track.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') { e.preventDefault(); go(current + 1); }
      if (e.key === 'ArrowLeft')  { e.preventDefault(); go(current - 1); }
    });

    // Keep the indicators honest when the user swipes or scrolls by hand.
    var settle;
    track.addEventListener('scroll', function () {
      clearTimeout(settle);
      settle = setTimeout(function () {
        var mid = track.scrollLeft + track.clientWidth / 2;
        var nearest = 0, best = Infinity;
        slides.forEach(function (s, n) {
          var c = (s.offsetLeft - track.offsetLeft) + s.offsetWidth / 2;
          if (Math.abs(c - mid) < best) { best = Math.abs(c - mid); nearest = n; }
        });
        paint(nearest);
      }, 90);
    }, { passive: true });

    paint(0);
  });
})();
