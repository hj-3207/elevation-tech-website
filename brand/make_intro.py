"""Render the Elevation Technology intro card as an h264 mp4.

    python brand/make_intro.py                      # 1920x1080 at 30fps
    python brand/make_intro.py --width 1556 --fps 25 --out C:/path/intro.mp4

Match the width, height and fps to the demo footage it goes in front of. Editors will
happily accept a mismatch and silently rescale, which softens the logo edges, and joining
clips of different sizes forces a re-encode of the whole timeline.

Visual language is lifted from the website so the intro and the site look related: near
black #080808 ground, the faint grid from .grid-bg, an orange glow behind the mark, and
the short orange rule the site uses under every section title.

Silent by design. No audio stream at all, so it drops in front of narration without a
gap or a level change to fix.

Needs: pillow, av. Fonts come from Windows: Consolas is what the site's mono stack falls
back to anyway, so the wordmark strap matches what a visitor sees.
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

LOGOS = {
    # The secondary lockup is the default because it carries the company name; the
    # primary reads only "ELEVATION".
    "secondary": "TechLogoSecondary-White.png",
    "primary": "TechLogoPrimary-White.png",
    "square": "TechLogoSquare-White.png",
}
MONO = "C:/Windows/Fonts/consola.ttf"


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


def grid_layer(w, h):
    """The site's .grid-bg: a faint lattice, just enough to stop the black reading as flat."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = max(28, w // 48)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 8), width=1)
    return layer


def glow_layer(w, h):
    """Orange bloom behind the mark, mirroring .hero-glow. Built small and scaled up so
    the gradient is smooth without computing a radius per pixel at full resolution."""
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


def build_frames(w, h, fps, seconds, logo_key="secondary", strap=""):
    total = int(round(fps * seconds))
    grid = grid_layer(w, h)
    glow = glow_layer(w, h)

    logo = Image.open(os.path.join(SITE, LOGOS[logo_key])).convert("RGBA")
    # Scale to a share of frame HEIGHT, not width, so the three lockups carry the same
    # optical weight despite their very different aspect ratios.
    target_h = int(h * 0.17)
    logo = logo.resize((round(logo.width * target_h / logo.height), target_h), Image.LANCZOS)

    font = ImageFont.truetype(MONO, max(11, int(w * 0.0105)))
    tracked = " ".join(strap)          # letter-spacing, which PIL will not do for us

    # Optically centre the group (logo, rule, and strap when present) instead of pinning
    # the logo to a fixed height. Without this the no-strap version sits high with dead
    # space under it.
    rule_off = int(h * 0.055)          # logo bottom to rule
    rule_h = max(2, int(h * 0.0028))
    strap_off = int(h * 0.105)         # logo bottom to strap top
    strap_h = font.size if strap else 0
    below = (strap_off + strap_h) if strap else (rule_off + rule_h)
    logo_top = (h - (logo.height + below)) // 2
    logo_cy = logo_top + logo.height // 2
    logo_bottom = logo_top + logo.height

    frames = []
    for i in range(total):
        t = i / (total - 1) if total > 1 else 1.0

        frame = Image.new("RGBA", (w, h), BG + (255,))
        frame.alpha_composite(Image.blend(Image.new("RGBA", (w, h), (0, 0, 0, 0)), grid, ramp(t, 0.00, 0.45)))

        # Glow leads the logo in slightly, so light arrives before the mark does.
        gl = ramp(t, 0.05, 0.55) * (0.55 + 0.45 * math.sin(min(1.0, t / 0.6) * math.pi / 2))
        if gl > 0:
            frame.alpha_composite(Image.blend(Image.new("RGBA", (w, h), (0, 0, 0, 0)), glow, min(1.0, gl)))

        # Logo: fade up while settling from 94% to full size.
        a = ramp(t, 0.10, 0.50)
        if a > 0:
            scale = 0.94 + 0.06 * ease_out((t - 0.10) / 0.40 if t > 0.10 else 0)
            sw, sh = max(1, int(logo.width * scale)), max(1, int(logo.height * scale))
            lg = logo.resize((sw, sh), Image.LANCZOS)
            if a < 1:
                lg.putalpha(lg.getchannel("A").point(lambda v, a=a: int(v * a)))
            frame.alpha_composite(lg, ((w - sw) // 2, logo_cy - sh // 2))

        # The site's .divider: a short orange rule, drawn outward from the centre.
        dv = ramp(t, 0.34, 0.62)
        if dv > 0:
            half = int(w * 0.045 * dv)
            y = logo_bottom + rule_off
            if half > 0:
                d = ImageDraw.Draw(frame)
                d.rectangle([w // 2 - half, y, w // 2 + half, y + rule_h],
                            fill=ORANGE_BRIGHT + (255,))

        # Strap line, last in and quietest.
        sa = ramp(t, 0.46, 0.72) if strap else 0
        if sa > 0:
            d = ImageDraw.Draw(frame)
            tw = d.textlength(tracked, font=font)
            y = logo_bottom + strap_off
            d.text(((w - tw) / 2, y), tracked, font=font,
                   fill=MUTED + (int(255 * sa),))

        # Single scanline sweep, the site's .scanline motif.
        if 0.18 < t < 0.85:
            sy = int((t - 0.18) / 0.67 * h)
            d = ImageDraw.Draw(frame)
            d.rectangle([0, sy, w, sy + max(1, h // 540)], fill=ORANGE + (26,))

        # Hold, then fade out. The last frame lands on clean black so a cut is invisible.
        if t > 0.82:
            k = (t - 0.82) / 0.18
            frame = Image.blend(frame, Image.new("RGBA", (w, h), BG + (255,)), min(1.0, k))

        frames.append(frame.convert("RGB"))
    return frames


def encode(frames, out, fps):
    w, h = frames[0].size
    w -= w % 2
    h -= h % 2
    container = av.open(out, "w")
    stream = container.add_stream("libx264", rate=Fraction(int(round(fps)), 1))
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    # crf 18 because flat dark gradients band badly at the usual 23.
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
    ap.add_argument("--seconds", type=float, default=3.4)
    ap.add_argument("--logo", choices=sorted(LOGOS), default="secondary")
    ap.add_argument("--strap", default="", help="optional line under the rule, e.g. \"HUNTING TOOLS THAT WORK OFFLINE\"")
    ap.add_argument("--out", default=os.path.join(HERE, "elevation-intro-1080p.mp4"))
    a = ap.parse_args()

    h = a.height or round(a.width * 9 / 16)
    frames = build_frames(a.width, h, a.fps, a.seconds, a.logo, a.strap)
    encode(frames, a.out, a.fps)
    print("wrote %s  %dx%d  %.1fs at %gfps  %.2f MB"
          % (a.out, a.width, h, a.seconds, a.fps, os.path.getsize(a.out) / 1e6))


if __name__ == "__main__":
    main()
