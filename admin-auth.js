/* Shared auth for the admin pages (license-admin.html, download-log.html).
 *
 * Both pages had their own copy of the session and token-refresh logic. Two copies of a
 * refresh path is the kind of duplication that goes wrong quietly: one gets a fix, the
 * other keeps the bug, and the symptom is an admin page that logs you out for no visible
 * reason. One copy now.
 *
 * Sign in happens on license-admin.html. The session lives in localStorage under one key,
 * so signing in there covers every admin page on the origin.
 *
 * The publishable key below is safe in public: it is the same key shipped inside the
 * desktop apps, and row level security is what actually gates the data. Signed out, every
 * table returns an empty array.
 */
window.LA = (function () {
  var URL_BASE = 'https://baopxmwebqfdubvgjsri.supabase.co';
  var ANON = 'sb_publishable_54t4NxwLHZqGuGNrDM9TrA_b7F3Dh3B';
  var STORE = 'la.session';

  function session() {
    try { return JSON.parse(localStorage.getItem(STORE)); } catch (e) { return null; }
  }

  function saveSession(s) {
    // A minute of headroom, so a request cannot start on a token that expires mid-flight.
    s.expires_at = Date.now() + ((s.expires_in || 3600) - 60) * 1000;
    localStorage.setItem(STORE, JSON.stringify(s));
  }

  function clearSession() { localStorage.removeItem(STORE); }

  function refresh(token) {
    return fetch(URL_BASE + '/auth/v1/token?grant_type=refresh_token', {
      method: 'POST',
      headers: { apikey: ANON, 'content-type': 'application/json' },
      body: JSON.stringify({ refresh_token: token })
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && j.access_token) { saveSession(j); return true; } return false; })
      .catch(function () { return false; });
  }

  function signIn(email, password) {
    return fetch(URL_BASE + '/auth/v1/token?grant_type=password', {
      method: 'POST',
      headers: { apikey: ANON, 'content-type': 'application/json' },
      body: JSON.stringify({ email: email, password: password })
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, body: j }; });
    }).then(function (res) {
      if (!res.ok || !res.body.access_token) {
        throw new Error(res.body.error_description || res.body.msg || 'Sign in failed.');
      }
      saveSession(res.body);
      return true;
    });
  }

  function authFetch(path, opts) {
    opts = opts || {};
    var s = session();
    var run = function (tok) {
      var h = opts.headers || {};
      h.apikey = ANON;
      h.Authorization = 'Bearer ' + tok;
      h['content-type'] = 'application/json';
      return fetch(URL_BASE + path, {
        method: opts.method || 'GET', headers: h, body: opts.body
      });
    };
    if (s && s.expires_at && Date.now() > s.expires_at && s.refresh_token) {
      return refresh(s.refresh_token).then(function (ok) {
        if (!ok) throw new Error('Session expired. Sign in again on the licence admin page.');
        return run(session().access_token);
      });
    }
    return run(s ? s.access_token : '');
  }

  return {
    URL_BASE: URL_BASE, ANON: ANON, STORE: STORE,
    session: session, saveSession: saveSession, clearSession: clearSession,
    refresh: refresh, signIn: signIn, authFetch: authFetch
  };
})();
