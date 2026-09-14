# Elevation Technology Solutions — website

Hand-written static site. **No build step, no framework, no dependencies, no
package.json.** Twelve public pages plus two unlinked admin pages, one shared
stylesheet and six small JS files. Edit a file, refresh the browser.

## Deploy

GitHub Pages, from `main` on `git@github.com:hj-3207/elevation-tech-website.git`.
Pushing to `main` publishes. Live at:

```
https://hj-3207.github.io/elevation-tech-website/
```

**The site is served from a subpath, not a domain root.** Never use
root-relative paths (`/img/foo.png`) — they resolve to `hj-3207.github.io/img/...`
and 404. Always relative (`img/foo.png`). This bit the web manifest once already.

## Local development

```bash
python -m http.server 8000 --bind 0.0.0.0     # from the repo root
```

- Desktop: <http://localhost:8000>
- Phone on the same WiFi: `http://<your-lan-ip>:8000` — the only real way to test
  the mobile nav and the responsive breakpoints.
- `file://` works too (every path is relative), but a server matches production
  more closely.
- **`Ctrl+F5` after editing `style.css` or any `.js`** — browsers cache them hard,
  and they are no longer inline.

⚠️ Over `http://localhost` the Supabase download counters actually fire, inserting
real rows into the production tables. Don't click Download buttons while testing.
(Over `file://` they fail on CORS and stay harmless.)

## The four apps

The software line is hunting tools. Two Windows programs and two mobile apps.

| App | Platform | Price | Delivery |
|---|---|---|---|
| Rack Detector | Windows 10/11 | $100 one-time, free to 10,000 images | OneDrive zip + Stripe |
| Rack Viewer | Windows 10/11 | Free to view forever; $20 one-time after 10 Keeper Cleanups | OneDrive exe + Stripe |
| Rack Tracker | Android | $10/year | Google Play `com.racktracker.app` |
| Rack Scorer | Android + iOS | $4.99 one-time, **no free trial** | Google Play `com.rackscorer.app` · App Store `id6807572200` |

Buying Rack Detector includes a Rack Viewer license.

**Rack Scorer shipped on the App Store on 2026-09-09 and is now Android + iOS.**
Rack Tracker is still Android-only, and its page and `apps.html` say an iOS version is
"in the works" — that line is a placeholder for a build that is not published yet, so
leave it until the App Store link arrives. Keep both halves true: don't let a rewrite
spread iOS to Tracker, and don't reintroduce "Android only" copy on Scorer.
(`id6807572200` was briefly published on Tracker's page in error on 2026-09-08 and
reverted the next day; it is Scorer's id.)

`apps.html` frames them as a workflow: **Sort → View → Track → Score**. Keep that
order and those verbs consistent wherever the four are listed together.

Every app is offline-first and stores data on the user's own device. That claim is
the core marketing argument of the whole site, so **do not weaken it, and do not
state it where it isn't true.** Rack Viewer's one-time license activation is the
single network call in the desktop line, and it is disclosed.

## Pages

- `index.html` — company home: about, services, apps grid, contact
- `apps.html` — the apps landing page
- `rack-{detector,viewer,tracker,scorer}.html` — one product page each
- `privacy-policy-rack{detector,viewer,tracker,scorer}.html`
- `terms-rack{detector,viewer}.html` — Tracker and Scorer have no terms page yet
- `privacy-policy-rackracker.html` — **typo filename, kept deliberately.** Was
  published first and may be linked externally; it redirects to the correct page.
- `google4f30917507f29334.html` — Search Console verification, do not touch
- `license-admin.html`, `download-log.html` — internal admin, `noindex`, and linked
  from nowhere. Reached by **Ctrl-clicking (or Cmd-clicking) the footer logo** on any
  page; the delegated handler is at the bottom of `nav.js`. Hidden, not secret — the
  repo is public, so the real gate is Supabase Auth plus RLS, which returns an empty
  array when signed out. `license-admin.html` can SELECT, UPDATE and INSERT, but **never
  DELETE** — nothing on the site can destroy inventory or alter a code that has been sent.
  Desktop keys are still minted offline by `gen_codes.py`; the INSERT path exists only for
  the Rack Scorer promo batches, via the Load panel described below. `version` is a product
  marker, not a release number: 7 is Rack Detector, 1001 is Rack Viewer, 2001 is Rack
  Scorer (Android) and 2002 is Rack Scorer (iOS).

**Rack Scorer's codes are store promo codes, and behave unlike the desktop ones.** They
are minted in Play Console and App Store Connect, redeemed inside the store, and Rack
Scorer makes no network call, so **no redemption is ever reported back.** Those two
products track one axis only: a code is in the pool, or it has been handed to someone.
The Activated columns read `n/a` for them on purpose — do not wire up an activated state
for Scorer, because it could only ever be typed in by hand, and a hand-typed guess in the
same column as a real activation stops looking like a guess within a week.

Android and iOS are **two products, not one with a platform column**, because a Play code
is useless to an iPhone buyer. This is deliberately the opposite call to the download
counters, where both stores share `downloads_rackscorer`.

`license_keys.expires_at` (timestamptz, nullable) exists for these: Apple's promo codes
die 28 days after generation, Play codes carry the end date you set. The admin page greys
out expired codes, flags anything inside a week, and excludes expired codes from the
Assign pool. Expiry is tracked **separately from state**, since a code can be unsent and
expired (dead inventory) or sent and expired (posted, never redeemed). Desktop codes
leave it null and are unaffected.

**Redemption links are built from the code, never stored.** Both are confirmed working
(2026-09-14):

- Play — `https://play.google.com/redeem?code=…`
- App Store — `https://apps.apple.com/redeem?code=…`, **no app id and no `ctx`**

Apple documents no redemption URL for app promo codes, so that second one was found by
testing, and two plausible-looking "corrections" both break it. Adding `id=6807572200` is
unnecessary — a promo code already identifies its own app. Switching to `ctx=offercodes`,
which every search result recommends, is wrong: that form is for *subscription and IAP
offer codes*, and Rack Scorer is a one-time paid app whose codes are plain app promo
codes. Leave `REDEEM[2002]` in `license-admin.html` as it is.

**Clicking a code in the admin table redeems it.** The links are live anchors, so a stray
click burns a code against whatever account the browser is signed in to, unrecoverably.
The `link` button beside each code copies the URL instead, which is what sending one
actually needs.

The Assign button hands out the **soonest-expiring** code first, and skips any code whose
tier is not `pro` on the desktop products — it used to be able to give a Rack Detector
giveaway code to a paying buyer without the unsold count moving. Sending a promo code on
purpose is what the row Edit button is for.

## Conventions

**Design tokens** live in `:root` in `style.css`. Burnt orange `#CC5500`, near-black
`#080808`, Inter + JetBrains Mono. Use the variables, never raw hex.

**Section pattern**, used by every section on every page:

```html
<div class="section-eyebrow">Eyebrow</div>     <!-- small orange mono, gets a // prefix -->
<div class="section-title">Title</div>          <!-- a div, NOT a heading element -->
<div class="divider"></div>
<p class="section-sub">Optional lead-in</p>
```

`.section-title` is presentational. Real document structure is `h1` then the `h2`s.

**Class prefixes**

- `rd-*` — the shared product-page shell (hero, buttons, features grid, price
  callout). Used by **all four** product pages, not just Rack Detector.
- `rt-*` — phone screenshots, privacy callout, screenshot carousel. Shared by
  `rack-tracker.html` and `rack-scorer.html`.
- `legal`, `legal-*` — policy and terms pages.
- `hero-f*`, `app-row`, `cmp*` — `apps.html` only, and defined in that page's own
  `<style>` block.

**Where CSS goes:** shared rules in `style.css`; rules used by exactly one page stay
in that page's `<style>` block. `apps.html` is the only *public* page with an inline
block; both admin pages carry their own too.

**Shared JS** — six files, each loaded with a plain `<script src>`:

- `nav.js` — mobile nav toggle, plus the Ctrl-click route to the admin page. All 12
  public pages.
- `lightbox.js` — click a content image to see it full size. All 12 public pages.
  Opt-in by selector, so logos and tile icons stay unclickable.
- `carousel.js` — screenshot carousel. `rack-tracker.html`, `rack-scorer.html`.
- `downloads.js` — store and download click counters. **All four** product pages.
  **Not** `apps.html`, which has no download buttons.
- `videotabs.js` — tabbed demo player. `rack-detector.html`, `rack-viewer.html`. It
  builds the iframe on click, so a visitor who never presses play never contacts
  YouTube at all. That matters on pages arguing the software collects nothing.
- `admin-auth.js` — shared Supabase session and token refresh. The two admin pages
  only. It exists because both had their own copy of the refresh path, and two copies
  of that goes wrong quietly. Keep it one copy.

## Things that will bite you

**The nav is duplicated across all 12 pages and must stay identical.** Five links —
home, about, services, apps, contact — in that order. Every page points at
`index.html#…`; `index.html` alone uses bare `#…` so it scrolls instead of
reloading. There is no templating, so changing the nav means changing 12 files.

**The nav is `position: fixed`,** so anchor targets need to reserve room or they
land underneath it. `style.css` handles this globally:

```css
section[id], .app-row[id] { scroll-margin-top: 100px; }
```

Any new anchor target must be a `section[id]` or carry that rule.

**Download links are OneDrive share links with stable filenames.** Upload each new
build **over** the existing file. Renaming keeps the link alive; deleting and
re-uploading creates a new item and breaks every link on the site.

**The four download counters use four separate Supabase tables.** `downloads` is Rack
Detector's and has no app column, so every other app writes to its own:
`downloads_rackviewer`, `downloads_racktracker`, `downloads_rackscorer`. Never merge
them — it would silently fold one app's clicks into another's count. Rack Scorer is
the one exception, and a deliberate one: its Google Play and App Store buttons both
write to `downloads_rackscorer`, so that figure is clicks for the app rather than per
platform. The publishable key in `downloads.js` is safe to expose: RLS permits insert
only. All of these count clicks, not installs.

**Purchase and download buttons belong on product pages only.** `apps.html`
deliberately links to the product pages instead, so nobody installs before reading
the system requirements (Rack Detector needs an NVIDIA GPU for usable speed).

**Rack Tracker screenshots 1–5 show real data** — real GPS coordinates in plain
text, real place names, and another hunter's name and photo. Published knowingly
(decided 2026-07-30). Do not add a "sample data only" disclaimer to that section;
it would be untrue. If they ever need pulling, note the images persist in git
history, so a deletion commit alone will not remove them.

## Copy voice

Terse, concrete, unglamorous. "No folded paper sheet, no arithmetic, no signal."
Avoid marketing filler — no "easily", "seamless", "it's a breeze", "powerful".
Say what the thing does and what it costs. Being straight about limitations is
part of the voice: the GPU warning, "non-refundable", and Rack Scorer's "Android only
for now".

Prices and trial terms appear in several places per app. When one changes, grep for
the old figure across every page — `index.html`, `apps.html`, the product page,
and the comparison table all carry them.

On `apps.html`, each app's **hero step card and its app-block lead paragraph carry
the same sentence, by design** — one canonical description per app. Change both
together, or the page starts telling two stories. The three bullets under each
lead are meant to add facts the lead does not state; keep them that way.

## Page titles

One convention, every page: `<Page> | Elevation Technology`. Legal pages use
`Rack Viewer Privacy Policy | Elevation Technology`. `index.html` carries
`Elevation Technology` alone, having no page name to sit in front of it.

Note the titles say "Elevation Technology" while the footer, logo alt text and
body copy all say "Elevation Technology **Solutions**". That shortening is
deliberate and confined to the tab title.

These titles are intentionally short. The product pages previously carried SEO
descriptors (`Rack Detector — AI Trail-Camera Photo Sorting | …`); those were
dropped for brevity, so the `<meta name="description">` on each page is now the
main place those keywords live. Do not strip the descriptions too.

## Known open items

- No terms page for Rack Tracker or Rack Scorer.
- Promo codes are loaded by **pasting them into the Load panel on `license-admin.html`**.
  `load_promo_codes.py`, alongside `gen_codes.py` outside this repo, does the same job as
  SQL and is the fallback if the page is broken. Store code lists carry no dates, so
  expiry is chosen at load time, and **the two stores need different settings.** Apple states a rule rather than a date, so iOS batches use
  "generated on" / `--generated YYYY-MM-DD` and get generation + 28 days at 12:00Z —
  midday because Apple does not publish what time of day they die. Play states an end
  date outright, so those
  use "good until" / `--expires YYYY-MM-DD` and get 23:59:59Z, the end of that day being
  what "good until the 1st" means. Do not assume Play is also 28 days: the 2026-09-14
  batch runs to 2027-01-01. Keep code lists and generated SQL out of this repo — they are unredeemed
  codes and the repo is public. **The codes cannot live in this repo instead of Supabase**
  — it is public, git history is permanent, and Pages has nothing to write to, so "handed
  out" could not be recorded at all. Asked and answered on 2026-09-14; the paste box was
  built to remove the trip to the SQL editor, which was the actual friction.
- Rack Scorer's App Store and Play Store clicks land in one counter table, so the
  admin cannot split them by platform. A fifth table would be the fix.
- `rack-scorer.html` embeds its demo with a plain `<iframe>` that loads with the page,
  while the Detector and Viewer tabs wait for a click. Both use `youtube-nocookie`, so
  no tracking cookie is set before play either way, but only the tabs avoid the
  request entirely.
- No `sitemap.xml` or `robots.txt`; `index.html` has no meta description.
- `index.html` lists the apps as Viewer, Detector, Tracker, Scorer, which
  contradicts the Sort → View → Track → Score order `apps.html` teaches.
- The comparison table's `min-width: 660px` forces sideways scrolling on a phone.
  Dropping its "What it does" column would likely fix that, and that column is a
  third restatement of each app's description; proposed and not taken.
- `apps.html` says "Rack Viewer **culls** them down to the keepers" in its meta
  description, though the step verb is now "View". Left as-is because *cull* reads
  fine as an ordinary verb there.
