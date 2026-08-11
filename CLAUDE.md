# Elevation Technology Solutions — website

Hand-written static site. **No build step, no framework, no dependencies, no
package.json.** Twelve HTML pages plus one shared stylesheet and three small JS
files. Edit a file, refresh the browser.

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

The software line is hunting tools. Two Windows programs, two Android apps.

| App | Platform | Price | Delivery |
|---|---|---|---|
| Rack Detector | Windows 10/11 | $100 one-time, free to 10,000 images | OneDrive zip + Stripe |
| Rack Viewer | Windows 10/11 | Free to view forever; $10 one-time after 10 Keeper Cleanups | OneDrive exe + Stripe |
| Rack Tracker | Android | $10/year | Google Play `com.racktracker.app` |
| Rack Scorer | Android | $4.99 one-time, **no free trial** | Google Play `com.rackscorer.app` |

Buying Rack Detector includes a Rack Viewer license. iOS versions are stated as
"in the works" — do not write copy implying an iOS build ships today.

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
in that page's `<style>` block. `apps.html` is the only page with an inline block.

**Shared JS** — three files, each loaded with a plain `<script src>`:

- `nav.js` — mobile nav toggle. Loaded by all 12 pages.
- `carousel.js` — screenshot carousel. `rack-tracker.html`, `rack-scorer.html`.
- `downloads.js` — download-click counters. `rack-detector.html`,
  `rack-viewer.html`. **Not** `apps.html`, which has no download buttons.

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

**The two download counters use separate Supabase tables.** `downloads` is Rack
Detector's and has no app column, so Rack Viewer writes to `downloads_rackviewer`.
Never merge them — it would silently fold Viewer clicks into Detector's count. The
publishable key in `downloads.js` is safe to expose: RLS permits insert only.

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
part of the voice: the GPU warning, "non-refundable", "Android only for now".

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
- Rack Detector and Rack Viewer demo videos are still `Demo video coming soon`
  placeholders. Rack Scorer has a real embed (`youtube-nocookie`, chosen so no
  tracking cookie is set before the visitor hits play).
- No `sitemap.xml` or `robots.txt`; `index.html` has no meta description.
- `index.html` lists the apps as Viewer, Detector, Tracker, Scorer, which
  contradicts the Sort → View → Track → Score order `apps.html` teaches.
- The comparison table's `min-width: 660px` forces sideways scrolling on a phone.
  Dropping its "What it does" column would likely fix that, and that column is a
  third restatement of each app's description; proposed and not taken.
- `apps.html` says "Rack Viewer **culls** them down to the keepers" in its meta
  description, though the step verb is now "View". Left as-is because *cull* reads
  fine as an ordinary verb there.
