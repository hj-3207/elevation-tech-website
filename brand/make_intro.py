"""Render an Elevation intro card, or a two-card intro, as a silent h264 mp4.

    # brand card only
    python brand/make_intro.py --out C:/path/intro.mp4

    # brand card, then a product card naming what the video demonstrates
    python brand/make_intro.py --product viewer --title SPEED \
        --width 1598 --height 852 --fps 30 --out C:/path/viewer-speed.mp4

Match width, height and fps to the footage it precedes. An editor will accept a mismatch
and silently rescale, which softens the logo, and joining clips of different sizes forces
a re-encode of the whole timeline. DetectorDemo.mp4 is 1598x852 at 30fps.

Visual language comes from the website so the intro and the site look related: the near
black #080808 ground, the faint grid from .grid-bg, an orange bloom, and the short orange
rule that sits under every section title.

Silent by design, with no audio stream at all.

PRODUCT LOGOS ARE BLACK ARTWORK. img/rackdetector-logo.png and img/rackviewer-logo.png are
pure black ink with the anti-aliasing carried in the alpha channel, so they are invisible
on a dark ground. They are recoloured to near-white at render time, alpha preserved, which
is the same relationship TechLogoPrimary.png and TechLogoPrimary-White.png already have.
No white variant of the product logos exists on disk.

Needs: pillow, av.
"""

import argparse
import math
import os
from fractions import Fraction

import av
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)

BG = (8, 8, 8)                  # --bg
ORANGE = (204, 85, 0)           # --orange
ORANGE_BRIGHT = (224, 96, 16)   # --orange-bright
MUTED = (119, 119, 119)         # --muted
INK = (245, 245, 245)           # near white, not pure, so it does not glare on dark

BRAND_LOGOS = {
    # Secondary carries "ELEVATION TECH SOLUTIONS"; primary reads only "ELEVATION".
    "secondary": "TechLogoSecondary-White.png",
    "primary": "TechLogoPrimary-White.png",
    "square": "TechLogoSquare-White.png",
}
PRODUCT_LOGOS = {
    "detector": "img/rackdetector-logo.png",
    "viewer": "img/rackviewer-logo.png",
}
MONO = "C:/Windows/Fonts/consola.ttf"
DEFAULT_STRAP = "HUNTING SOFTWARE BUILT BY HUNTERS"


def ease_out(t):
    """Cubic ease-out. Fast to start, settles gently, so nothing snaps into place."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ramp(t, start, end):
    """0 before start, 1 after end, eased between."""
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    return ease_out((t - start) / (end - start))


def whiten(im):
    """Recolour single-colour artwork to near-white, keeping its alpha. The product logos
    are black ink with anti-aliasing in the alpha channel, so this preserves every edge."""
    out = Image.new("RGBA", im.size, INK + (255,))
    out.putalpha(im.getchannel("A"))
    return out


def load_logo(path, frame_h, share, recolour):
    im = Image.open(os.path.join(SITE, path)).convert("RGBA")
    if recolour:
        im = whiten(im)
    # Scale by a share of frame HEIGHT, so different lockups carry the same optical weight.
    target_h = max(1, int(frame_h * share))
    return im.resize((max(1, round(im.width * target_h / im.height)), target_h), Image.LANCZOS)


def grid_layer(w, h):
    """The site's .grid-bg: enough lattice to stop the black reading as flat."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = max(28, w // 48)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 8), width=1)
    return layer


def glow_layer(w, h):
    """Orange bloom, mirroring .hero-glow. Computed at 160px and scaled up: a falloff this
    smooth does not need evaluating per pixel at full resolution."""
    small = 160
    g = Image.new("L", (small, small), 0)
    px = g.load()
    c = (small - 1) / 2
    for y in range(small):
        for x in range(small):
            r = math.hypot(x - c, y - c) / c
            px[x, y] = int(max(0.0, 1.0 - r) ** 2.2 * 90) if r < 1 else 0
    mask = g.resize((int(w * 0.95), int(w * 0.95)), Image.BICUBIC)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tint = Image.new("RGBA", mask.size, ORANGE + (255,))
    layer.paste(tint, ((w - mask.size[0]) // 2, (h - mask.size[1]) // 2 - int(h * 0.02)), mask)
    return layer


def card_layer(w, h, logo, line, font, p, colour=MUTED, scale=1.0):
    """One card's content on transparency. p is 0..1 through that card.

    Elements arrive staggered: logo, then the rule drawn outward from the centre, then the
    line. Staggering is what makes it read as composed rather than mechanical.
    """
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    rule_off = int(h * 0.055)
    rule_h = max(2, int(h * 0.0028))
    line_off = int(h * 0.105)
    if scale != 1.0 and line:
        font = ImageFont.truetype(MONO, max(11, int(font.size * scale)))
    line_h = font.size if line else 0
    below = (line_off + line_h) if line else (rule_off + rule_h)
    logo_top = (h - (logo.height + below)) // 2
    logo_bottom = logo_top + logo.height

    a = ramp(p, 0.00, 0.55)
    if a > 0:
        scale = 0.94 + 0.06 * ease_out(p / 0.45 if p < 0.45 else 1.0)
        sw, sh = max(1, int(logo.width * scale)), max(1, int(logo.height * scale))
        lg = logo.resize((sw, sh), Image.LANCZOS)
        if a < 1:
            lg.putalpha(lg.getchannel("A").point(lambda v, a=a: int(v * a)))
        layer.alpha_composite(lg, ((w - sw) // 2, (logo_top + logo.height // 2) - sh // 2))

    dv = ramp(p, 0.28, 0.60)
    if dv > 0:
        half = int(w * 0.045 * dv)
        if half > 0:
            d = ImageDraw.Draw(layer)
            y = logo_bottom + rule_off
            d.rectangle([w // 2 - half, y, w // 2 + half, y + rule_h], fill=ORANGE_BRIGHT + (255,))

    la = ramp(p, 0.40, 0.70) if line else 0
    if la > 0:
        d = ImageDraw.Draw(layer)
        tracked = " ".join(line)        # letter-spacing, which PIL will not do for us
        tw = d.textlength(tracked, font=font)
        d.text(((w - tw) / 2, logo_bottom + line_off), tracked, font=font,
               fill=colour + (int(255 * la),))
    return layer


def build(w, h, fps, cards, card_seconds, crossfade):
    """cards is a list of (logo image, line). Cards overlap by `crossfade` seconds, and
    each fades in and out at its own edges, so the overlap dissolves one into the next."""
    step = card_seconds - crossfade
    total_s = card_seconds + step * (len(cards) - 1)
    n = max(1, int(round(fps * total_s)))

    grid = grid_layer(w, h)
    glow = glow_layer(w, h)
    font = ImageFont.truetype(MONO, max(11, int(w * 0.0105)))
    blank = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    frames = []
    for i in range(n):
        T = i / fps
        g = i / (n - 1) if n > 1 else 1.0          # global position, for grid and fade out

        frame = Image.new("RGBA", (w, h), BG + (255,))
        frame.alpha_composite(Image.blend(blank, grid, ramp(g, 0.00, 0.18)))

        gl = ramp(g, 0.03, 0.30)
        if gl > 0:
            frame.alpha_composite(Image.blend(blank, glow, min(1.0, gl * 0.9)))

        for idx, (logo, line, colour, scale) in enumerate(cards):
            start = idx * step
            p = (T - start) / card_seconds
            if p < 0 or p > 1:
                continue
            # Fade the card in and out at its edges; with the overlap this is the dissolve.
            edge = crossfade / card_seconds if crossfade > 0 else 0.001
            alpha = min(1.0,
                        p / edge if p < edge else 1.0,
                        (1 - p) / edge if p > 1 - edge else 1.0)
            content = card_layer(w, h, logo, line, font, p, colour, scale)
            if alpha < 1:
                content.putalpha(content.getchannel("A").point(lambda v, a=alpha: int(v * a)))
            frame.alpha_composite(content)

        # One scanline sweep across the whole clip, the site's .scanline motif.
        if 0.10 < g < 0.90:
            sy = int((g - 0.10) / 0.80 * h)
            ImageDraw.Draw(frame).rectangle([0, sy, w, sy + max(1, h // 540)],
                                           fill=ORANGE + (26,))

        # Land on clean black, so the cut into the footage is invisible.
        if g > 0.88:
            frame = Image.blend(frame, Image.new("RGBA", (w, h), BG + (255,)),
                                min(1.0, (g - 0.88) / 0.12))

        frames.append(frame.convert("RGB"))
    return frames


def encode(frames, out, fps):
    w, h = frames[0].size
    w -= w % 2
    h -= h % 2
    container = av.open(out, "w")
    stream = container.add_stream("libx264", rate=Fraction(int(round(fps)), 1))
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    # crf 18 rather than 23: this frame is almost entirely flat dark gradient, which bands.
    stream.options = {"crf": "18", "preset": "slow", "movflags": "faststart"}
    for f in frames:
        if f.size != (w, h):
            f = f.resize((w, h), Image.LANCZOS)
        for p in stream.encode(av.VideoFrame.from_image(f)):
            container.mux(p)
    for p in stream.encode():
        container.mux(p)
    container.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=None, help="defaults to 16:9 of width")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--logo", choices=sorted(BRAND_LOGOS), default="secondary")
    ap.add_argument("--strap", default=DEFAULT_STRAP, help='"" to omit')
    ap.add_argument("--product", choices=sorted(PRODUCT_LOGOS), default=None,
                    help="adds a second card with that product's logo")
    ap.add_argument("--title", default="",
                    help="what the video demonstrates, e.g. SPEED. The product logo already "
                         "names the product, so this only needs the topic.")
    ap.add_argument("--card-seconds", type=float, default=2.6)
    ap.add_argument("--crossfade", type=float, default=0.55)
    ap.add_argument("--out", default=os.path.join(HERE, "elevation-intro.mp4"))
    a = ap.parse_args()

    h = a.height or round(a.width * 9 / 16)

    # The brand strap is a quiet tagline. The product title names what the video
    # actually shows, so it is brighter and larger. The product lockup also gets a
    # bigger share, because its wordmark is small relative to the antler above it.
    cards = [(load_logo(BRAND_LOGOS[a.logo], h, 0.17, recolour=False),
              a.strap, MUTED, 1.0)]
    if a.product:
        cards.append((load_logo(PRODUCT_LOGOS[a.product], h, 0.26, recolour=True),
                      a.title.upper(), (229, 229, 229), 1.6))

    frames = build(a.width, h, a.fps, cards, a.card_seconds, a.crossfade)
    encode(frames, a.out, a.fps)
    print("wrote %s  %dx%d  %d cards  %.1fs at %gfps  %.2f MB"
          % (a.out, a.width, h, len(cards), len(frames) / a.fps, a.fps,
             os.path.getsize(a.out) / 1e6))


if __name__ == "__main__":
    main()
