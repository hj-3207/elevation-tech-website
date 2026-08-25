/* Demo video tabs: one player, the topics as buttons above it.
 *
 * Nothing is requested from YouTube until a visitor actually asks for a video. The
 * iframe is built on click, not on page load, so someone who reads the page and leaves
 * never touches youtube-nocookie.com at all. That matters on pages whose argument is
 * that the software collects nothing.
 *
 * A tab with an empty data-yt shows the "coming soon" state, so the section can ship
 * before every video is uploaded.
 */
(function () {
  var groups = document.querySelectorAll('[data-vtabs]');
  if (!groups.length) return;

  Array.prototype.forEach.call(groups, function (group) {
    var tabs = group.querySelectorAll('.vtab');
    var stage = group.querySelector('[data-vstage]');
    var cap = group.querySelector('[data-vcap]');
    if (!tabs.length || !stage) return;

    function poster(tab) {
      var id = tab.getAttribute('data-yt');
      var label = id ? 'Watch: ' + tab.textContent.trim() : 'Demo video coming soon';
      stage.innerHTML = '<div class="video-placeholder">' +
        '<div class="play">&#9654;</div><span>' + label + '</span></div>';
      stage.setAttribute('data-ready', id ? 'yes' : 'no');
    }

    function select(tab) {
      Array.prototype.forEach.call(tabs, function (t) {
        var on = t === tab;
        t.classList.toggle('is-on', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
      });
      if (cap) cap.textContent = tab.getAttribute('data-cap') || '';
      poster(tab);                       // switching tabs stops whatever was playing
    }

    function play() {
      var tab = group.querySelector('.vtab.is-on');
      var id = tab && tab.getAttribute('data-yt');
      if (!id) return;
      var f = document.createElement('iframe');
      // nocookie, and autoplay only because the visitor just clicked to start it.
      f.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0';
      f.title = tab.getAttribute('data-title') || tab.textContent.trim();
      f.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
      f.setAttribute('allowfullscreen', '');
      stage.innerHTML = '';
      stage.appendChild(f);
    }

    Array.prototype.forEach.call(tabs, function (tab, i) {
      tab.addEventListener('click', function () { select(tab); });
      tab.addEventListener('keydown', function (e) {
        var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (!d) return;
        e.preventDefault();
        var next = tabs[(i + d + tabs.length) % tabs.length];
        next.focus();
        select(next);
      });
    });

    stage.addEventListener('click', function () { play(); });
    stage.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); play(); }
    });
    stage.tabIndex = 0;
    stage.setAttribute('role', 'button');

    select(group.querySelector('.vtab.is-on') || tabs[0]);
  });
})();
