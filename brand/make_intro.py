"""Render an Elevation intro as a silent h264 mp4. One brand card, optionally followed by
a product card naming what the video demonstrates.

    python brand/make_intro.py --style ridge --product viewer --title SPEED \
        --width 1598 --height 852 --fps 30 --out C:/path/viewer-speed.mp4

Match width, height and fps to the footage it precedes. An editor will accept a mismatch
and silently rescale, which softens the logo, and joining clips of different sizes forces
a re-encode of the whole timeline. DetectorDemo.mp4 is 1598x852 at 30fps.

STYLES, all on the site's palette and its mono face:
  grid     the site's .grid-bg lattice, orange bloom, one scanline sweep. Restrained.
  ridge    drifting topographic contours. Outdoors as data, which is what these apps are.
  profile  an elevation profile plots left to right like an instrument, and the lockup
           lands above the apex. Terrain read by a machine.
  mask     the mountain mark itself grows and its silhouette wipes one card into the next,
           so the logo is the transition rather than an object sitting on top of it.

Silent by design, with no audio stream at all.

PRODUCT LOGOS ARE BLACK ARTWORK. img/rackdetector-logo.png and img/rackviewer-logo.png are
pure black ink with anti-aliasing carried in the alpha channel, so they vanish on a dark
ground. They are recoloured to near-white at render time, alpha preserved, which is the
relationship TechLogoPrimary.png and TechLogoPrimary-White.png already have. No white
variant of either product logo exists on disk.

Fonts: the site asks for Inter and JetBrains Mono, neither of which is installed here.
Consolas is what the site's mono stack actually falls back to on Windows, so the small
letterspaced labels match what a visitor sees.

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
CARD = (17, 17, 17)             # --card
ORANGE = (204, 85, 0)           # --orange
ORANGE_BRIGHT = (224, 96, 16)   # --orange-bright
TEXT = (229, 229, 229)          # --text
MUTED = (119, 119, 119)         # --muted
INK = (245, 245, 245)           # near white, so recoloured art does not glare

BRAND_LOGOS = {
    "secondary": "TechLogoSecondary-White.png",   # carries "ELEVATION TECH SOLUTIONS"
    "primary": "TechLogoPrimary-White.png",       # reads only "ELEVATION"
    "square": "TechLogoSquare-White.png",
}
PRODUCT_LOGOS = {
    "detector": "img/rackdetector-logo.png",
    "viewer": "img/rackviewer-logo.png",
}
STYLES = ("grid", "ridge", "profile", "mask")
MONO = "C:/Windows/Fonts/consola.ttf"
DEFAULT_STRAP = "HUNTING SOFTWARE BUILT BY HUNTERS"


# ---------------------------------------------------------------- easing helpers

def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


def ramp(t, start, end, fn=ease_out):
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    return fn((t - start) / (end - start))


# ---------------------------------------------------------------- artwork

def whiten(im):
    """Recolour single-colour artwork to near-white, keeping alpha. The product logos are
    black ink whose anti-aliasing lives in the alpha channel, so every edge survives."""
    out = Image.new("RGBA", im.size, INK + (255,))
    out.putalpha(im.getchannel("A"))
    return out


def load_logo(path, frame_h, share, recolour):
    im = Image.open(os.path.join(SITE, path)).convert("RGBA")
    if recolour:
        im = whiten(im)
    target_h = max(1, int(frame_h * share))
    return im.resize((max(1, round(im.width * target_h / im.height)), target_h), Image.LANCZOS)


def extract_mark():
    """Just the mountain mark from the primary lockup, for the mask transition.

    Found rather than hardcoded: collect the columns that contain any ink, then cut at the
    widest empty gap. The mark is the cluster before that gap, the wordmark after it. This
    survives the logo being re-exported at another size.
    """
    im = Image.open(os.path.join(SITE, BRAND_LOGOS["primary"])).convert("RGBA")
    a = im.getchannel("A")
    cols = [x for x in range(im.width) if a.crop((x, 0, x + 1, im.height)).getextrema()[1] > 8]
    if not cols:
        return im
    gap_at, gap_len, run = cols[0], 0, cols[0]
    for prev, cur in zip(cols, cols[1:]):
        if cur - prev > gap_len:
            gap_len, gap_at = cur - prev, prev
    if gap_len < im.width * 0.02:          # no clear split, use the whole thing
        return im
    return im.crop((cols[0], 0, gap_at + 1, im.height))


# ---------------------------------------------------------------- backgrounds

def grid_layer(w, h):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = max(28, w // 48)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 8), width=1)
    return layer


def glow_layer(w, h):
    """Orange bloom, mirroring .hero-glow. Computed at 160px and scaled: a falloff this
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


def ridge_points(w, h, seed_phase, base_frac, amp_frac):
    """A ridgeline: a few sines at different frequencies, which reads as terrain because
    real terrain is also broadband. Sampled every 6px and drawn as a polyline."""
    pts = []
    amp = h * amp_frac
    for x in range(0, w + 6, 6):
        u = x / w
        y = (h * base_frac
             - amp * (0.55 * math.sin(u * 5.1 + seed_phase)
                      + 0.28 * math.sin(u * 11.3 + seed_phase * 1.7)
                      + 0.17 * math.sin(u * 23.7 + seed_phase * 2.3)))
        pts.append((x, y))
    return pts


def bg_ridge(w, h, g):
    """Drifting contours. Lines rise slowly and fade at the top, like a map redrawing."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = 11
    for i in range(n):
        k = (i / n + g * 0.12) % 1.0                  # drift upward over the clip
        y_base = 1.12 - k * 1.25
        if y_base < -0.05 or y_base > 1.15:
            continue
        fade = min(1.0, (1.0 - abs(y_base - 0.55) / 0.95))
        alpha = int(120 * max(0.0, fade) * ramp(g, 0.0, 0.22))
        if alpha <= 1:
            continue
        pts = ridge_points(w, h, 0.7 * i, y_base, 0.055 + 0.02 * math.sin(i))
        d.line(pts, fill=ORANGE + (alpha,), width=max(1, h // 420), joint="curve")
    return layer


def bg_profile(w, h, g):
    """One bold profile plotted left to right, filled beneath, with a cursor at the head.
    Reads as an instrument drawing terrain rather than a decorative squiggle."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    reveal = ramp(g, 0.02, 0.62, ease_in_out)
    if reveal <= 0:
        return layer
    pts = ridge_points(w, h, 1.3, 0.80, 0.16)
    cut = max(2, int(len(pts) * reveal))
    seen = pts[:cut]
    d.polygon(seen + [(seen[-1][0], h), (0, h)], fill=(26, 12, 4, 210))
    d.line(seen, fill=ORANGE_BRIGHT + (150,), width=max(2, h // 380), joint="curve")
    if reveal < 1.0:
        hx, hy = seen[-1]
        d.line([(hx, hy - h * 0.05), (hx, h)], fill=ORANGE_BRIGHT + (60,), width=max(1, h // 800))
        r = max(2, h // 260)
        d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=ORANGE_BRIGHT + (230,))
    return layer


# ---------------------------------------------------------------- cards

def card_layer(w, h, logo, line, font, p, colour=MUTED, scale=1.0, lift=0.0):
    """One card's content on transparency. p is 0..1 through that card.

    Elements arrive staggered: logo, then the rule drawn outward from the centre, then the
    line. Staggering is what makes it read as composed rather than mechanical.
    """
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if scale != 1.0 and line:
        font = ImageFont.truetype(MONO, max(11, int(font.size * scale)))

    rule_off = int(h * 0.055)
    rule_h = max(2, int(h * 0.0028))
    line_off = int(h * 0.105)
    line_h = font.size if line else 0
    below = (line_off + line_h) if line else (rule_off + rule_h)
    logo_top = (h - (logo.height + below)) // 2 - int(h * lift)
    logo_bottom = logo_top + logo.height

    a = ramp(p, 0.00, 0.42)
    if a > 0:
        sc = 0.94 + 0.06 * ease_out(p / 0.36 if p < 0.36 else 1.0)
        sw, sh = max(1, int(logo.width * sc)), max(1, int(logo.height * sc))
        lg = logo.resize((sw, sh), Image.LANCZOS)
        if a < 1:
            lg.putalpha(lg.getchannel("A").point(lambda v, a=a: int(v * a)))
        layer.alpha_composite(lg, ((w - sw) // 2, (logo_top + logo.height // 2) - sh // 2))

    dv = ramp(p, 0.22, 0.48)
    if dv > 0:
        half = int(w * 0.045 * dv)
        if half > 0:
            y = logo_bottom + rule_off
            ImageDraw.Draw(layer).rectangle(
                [w // 2 - half, y, w // 2 + half, y + rule_h], fill=ORANGE_BRIGHT + (255,))

    la = ramp(p, 0.32, 0.58) if line else 0
    if la > 0:
        d = ImageDraw.Draw(layer)
        tracked = " ".join(line)          # letter-spacing, which PIL will not do for us
        tw = d.textlength(tracked, font=font)
        d.text(((w - tw) / 2, logo_bottom + line_off), tracked, font=font,
               fill=colour + (int(255 * la),))
    return layer


# ---------------------------------------------------------------- assembly

def build(w, h, fps, cards, card_seconds, crossfade, style):
    step = card_seconds - crossfade
    total_s = card_seconds + step * (len(cards) - 1)
    n = max(1, int(round(fps * total_s)))

    grid = grid_layer(w, h)
    glow = glow_layer(w, h)
    font = ImageFont.truetype(MONO, max(11, int(w * 0.0105)))
    blank = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mark = extract_mark() if style == "mask" else None
    # profile puts terrain along the bottom, so the lockup lifts clear of it
    lift = 0.10 if style == "profile" else 0.0

    frames = []
    for i in range(n):
        T = i / fps
        g = i / (n - 1) if n > 1 else 1.0

        frame = Image.new("RGBA", (w, h), BG + (255,))

        if style in ("grid", "mask"):
            frame.alpha_composite(Image.blend(blank, grid, ramp(g, 0.00, 0.18)))
        gl = ramp(g, 0.03, 0.30)
        if gl > 0 and style != "profile":
            frame.alpha_composite(Image.blend(blank, glow, min(1.0, gl * (0.6 if style == "ridge" else 0.9))))
        if style == "ridge":
            frame.alpha_composite(bg_ridge(w, h, g))
        elif style == "profile":
            frame.alpha_composite(bg_profile(w, h, g))

        rendered = []
        for idx, (logo, line, colour, scale) in enumerate(cards):
            start = idx * step
            p = (T - start) / card_seconds
            if p < 0 or p > 1:
                rendered.append(None)
                continue
            rendered.append((idx, p, card_layer(w, h, logo, line, font, p, colour, scale, lift)))

        active = [r for r in rendered if r]
        if style == "mask" and len(active) == 2:
            # The mark grows from the centre and its silhouette wipes card two in, so the
            # logo performs the transition instead of sitting on top of one.
            (_, p0, c0), (_, p1, c1) = active
            frame.alpha_composite(c0)
            grow = ease_in_out(min(1.0, max(0.0, p1 / (crossfade / card_seconds))))
            target_h = max(2, int(h * (0.12 + 3.4 * grow)))
            mk = mark.resize((max(1, round(mark.width * target_h / mark.height)), target_h),
                             Image.LANCZOS)
            m = Image.new("L", (w, h), 0)
            m.paste(mk.getchannel("A"), ((w - mk.width) // 2, (h - mk.height) // 2))
            # Show the mark doing the wiping. Without this the reveal reads as a glitch:
            # you see half a wordmark appear with no visible cause. Fades out as the
            # shape outgrows the frame and stops being readable as a mountain.
            edge_a = int(150 * (1.0 - ease_in_out(min(1.0, grow / 0.62))))
            if edge_a > 2:
                tint = Image.new("RGBA", (w, h), ORANGE_BRIGHT + (0,))
                tint.putalpha(m.point(lambda v, a=edge_a: v * a // 255))
                frame.alpha_composite(tint)
            frame.paste(c1, (0, 0), Image.composite(c1.getchannel("A"), Image.new("L", (w, h), 0), m))
        else:
            for idx, p, content in active:
                edge = (crossfade / card_seconds) if crossfade > 0 else 0.001
                alpha = min(1.0,
                            p / edge if p < edge else 1.0,
                            (1 - p) / edge if p > 1 - edge else 1.0)
                if alpha < 1:
                    content.putalpha(content.getchannel("A").point(
                        lambda v, a=alpha: int(v * a)))
                frame.alpha_composite(content)

        if style == "grid" and 0.10 < g < 0.90:
            sy = int((g - 0.10) / 0.80 * h)
            ImageDraw.Draw(frame).rectangle([0, sy, w, sy + max(1, h // 540)],
                                           fill=ORANGE + (26,))

        if g > 0.90:
            frame = Image.blend(frame, Image.new("RGBA", (w, h), BG + (255,)),
                                min(1.0, (g - 0.90) / 0.10))
        frames.append(frame.convert("RGB"))
    return frames


def encode(frames, out, fps):
    w, h = frames[0].size
    w -= w % 2
    h -= h % 2
    container = av.open(out, "w")
    stream = container.add_stream("libx264", rate=Fraction(int(round(fps)), 1))
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    # crf 18 rather than 23: these frames are almost entirely flat dark gradient, and dark
    # gradients band badly at 23.
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
    ap.add_argument("--style", choices=STYLES, default="grid")
    ap.add_argument("--logo", choices=sorted(BRAND_LOGOS), default="secondary")
    ap.add_argument("--strap", default=DEFAULT_STRAP, help='"" to omit')
    ap.add_argument("--product", choices=sorted(PRODUCT_LOGOS), default=None)
    ap.add_argument("--title", default="",
                    help="what the video demonstrates, e.g. SPEED. The product logo already "
                         "names the product, so this only needs the topic.")
    ap.add_argument("--card-seconds", type=float, default=3.6)
    ap.add_argument("--crossfade", type=float, default=0.6)
    ap.add_argument("--out", default=os.path.join(HERE, "elevation-intro.mp4"))
    a = ap.parse_args()

    h = a.height or round(a.width * 9 / 16)

    # The brand strap is a quiet tagline. The product title is what the viewer came for, so
    # it is brighter and larger. The product lockup takes a bigger share of frame height
    # because its wordmark is small next to the antler above it.
    cards = [(load_logo(BRAND_LOGOS[a.logo], h, 0.17, False), a.strap, MUTED, 1.0)]
    if a.product:
        cards.append((load_logo(PRODUCT_LOGOS[a.product], h, 0.26, True),
                      a.title.upper(), TEXT, 1.6))

    frames = build(a.width, h, a.fps, cards, a.card_seconds, a.crossfade, a.style)
    encode(frames, a.out, a.fps)
    print("wrote %s  %s  %dx%d  %d cards  %.1fs at %gfps  %.2f MB"
          % (os.path.basename(a.out), a.style, a.width, h, len(cards),
             len(frames) / a.fps, a.fps, os.path.getsize(a.out) / 1e6))


if __name__ == "__main__":
    main()
