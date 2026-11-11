"""Pastveil Mysteries' thumbnail: "Historical Mystery" documentary poster.

Obsidian, midnight navy, antique gold and one dark crimson, inside a thin
engraved gold frame. One cinematic historical subject fills the left of a
long card and a navy "veil" darkens the right, where the headline sits
left-aligned: the lead-in in letter-spaced Montserrat gold, the key word in
engraved Cinzel, a gold rule closed by a crimson wax seal with a compass star,
and a crimson case-file strip ("UNSOLVED CASE"). The logo sits top right.
Shorts get a 1080x1920 card: a small logo top left, the subject in the
upper two thirds, the headline block below it.

Deliberately unlike the true-story card (story_thumbnail.py: a centred name
on a red brush stroke) so the two channels never look alike.

    channels.json: "thumbnail_style": "mystery"

The channel's saved style guide (data/brand/<id>/style.md) steers the
headline and the picture. A logo with real transparency at
data/brand/<id>/logo.png replaces the drawn wordmark.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .config import settings

OBSIDIAN = (8, 12, 16)
NAVY = (11, 29, 42)
ANTIQUE_GOLD = (215, 163, 74)
ROYAL_GOLD = (243, 198, 108)
CRIMSON = (104, 26, 27)
IVORY = (240, 229, 206)
SANDSTONE = (169, 120, 67)

FONTS = settings.root / "fonts"

_STYLE = ("Cinematic photorealistic historical documentary key art, dramatic golden-hour sunlight or deep "
          "blue moonlight, weathered stone and ancient metal, deep navy and black shadows, warm amber "
          "highlights, subtle atmospheric haze, rich contrast, high detail, premium film still. No text, no "
          "letters, no writing, no logos, no watermark, no frame, no cartoon, no neon, no modern objects.")
_PLACE_LONG = (" Wide 16:9 composition: the main subject large on the LEFT half of the frame; the RIGHT half "
               "is darker open sky or shadowed distant ruins with no important detail.")
_PLACE_SHORT = (" Vertical 9:16 composition: the main subject large in the upper two thirds; the lower third "
                "is darker ground and shadow.")
_TAGS = ["UNSOLVED CASE", "STILL UNEXPLAINED", "CASE FILE OPEN", "TRUTH STILL BURIED", "NEVER FOUND"]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    files = {"cinzel": "Cinzel-Black.ttf", "mont": "Montserrat-ExtraBold.ttf"}
    return ImageFont.truetype(str(FONTS / files[name]), max(8, int(size)))


def _ink_w(font, text: str) -> int:
    box = font.getbbox(text)
    return box[2] - box[0]


def _cap_h(font) -> int:
    box = font.getbbox("H")
    return box[3] - box[1]


# ------------------------------------------------------------------ the plan

def plan_for(title: str, guide: str = "", vertical: bool = False) -> dict:
    """Headline, scroll label and picture, written by the AI writer from the title."""
    from .genre_topics import _script_json

    guide_text = f"The channel's thumbnail style guide (follow it):\n{guide[:3000]}\n\n" if guide else ""
    plan = _script_json(
        guide_text
        + "Write the text for a premium historical-mystery documentary YouTube thumbnail.\n"
        f"Video title: {title}\n"
        'Return ONLY JSON: {"top": str, "big": str, "tag": str, "visual": str}.\n'
        "- top + big together are 2 to 5 words, the headline, all capitals. big is the ONE thing to "
        f"shout: 1 or 2 words, at most {9 if vertical else 12} letters, usually the place, people or "
        "object (\"EGYPT\", \"ROANOKE\", \"ATLANTIS?\"). top is the lead-in before it, 0 to 4 words "
        "(\"THE LOST CITY OF\", \"THE MYSTERY OF\", \"WHO BUILT\"). Keep a question mark when the title "
        "is a question.\n"
        "- tag: 2 to 4 words for a small crimson warning strip, all capitals, like a case-file stamp, "
        "not a repeat of the headline (\"UNSOLVED CASE\", \"STILL UNEXPLAINED\", \"NEVER FOUND\").\n"
        "- visual: one sentence for a photorealistic image of ONE dominant historical subject that "
        "belongs to THIS topic (its real ruin, statue, artifact, ship, temple or landscape, with real "
        "period details). Pyramids or a sphinx only when the topic is Egypt. A lone explorer with a "
        "lantern seen from behind is allowed; no close-up faces of real people. No text in the image.\n"
        "Never claim more than the title does."
    )
    clean = lambda value, limit: re.sub(r"\s+", " ", str(value or "")).strip().upper()[:limit]  # noqa: E731
    top, big = clean(plan.get("top"), 30), clean(plan.get("big"), 14)
    if not big:
        return fallback_plan(title, vertical)
    return {"top": top, "big": big, "tag": clean(plan.get("tag"), 26),
            "visual": str(plan.get("visual") or title).strip()[:400]}


_FILLER = {"the", "a", "an", "of", "in", "and", "to", "for", "is", "was", "what", "really", "happened",
           "inside", "finally", "explained", "why", "how", "who", "did", "does"}


def fallback_plan(title: str, vertical: bool = False) -> dict:
    """A headline straight from the title, for when no AI writer answers."""
    clean = re.sub(r"\s*[|:–—]\s.*$", "", title).strip()
    question = clean.endswith("?")
    words = re.findall(r"[A-Za-z0-9']+", clean)
    limit = 9 if vertical else 12
    keys = [w for w in words if w.lower() not in _FILLER]
    big = next((w for w in reversed(keys) if len(w) <= limit), (keys or words or ["MYSTERY"])[-1][:limit])
    cut = words.index(big) if big in words else len(words)
    top = " ".join(words[max(0, cut - 4):cut])
    return {"top": top.upper()[:30], "big": (big + ("?" if question else "")).upper(),
            "tag": "", "visual": f"{clean}, ancient historical site, cinematic documentary scene"}


# ------------------------------------------------------------------ drawing pieces

def _cover(image: Image.Image, w: int, h: int, focus_x: float = 0.5) -> Image.Image:
    scale = max(w / image.width, h / image.height)
    image = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))), Image.LANCZOS)
    left = int((image.width - w) * focus_x)
    top = (image.height - h) // 2
    return image.crop((left, top, left + w, top + h))


def _grade(image: Image.Image) -> Image.Image:
    """Filmic: a touch more contrast, gently warm highlights, no glow."""
    image = ImageEnhance.Contrast(image).enhance(1.12)
    image = ImageEnhance.Color(image).enhance(1.04)
    r, g, b = image.split()
    r = r.point(lambda v: min(255, int(v * 1.03)))
    b = b.point(lambda v: int(v * 0.96))
    return Image.merge("RGB", (r, g, b))


def _shade(w: int, h: int, alpha_at) -> Image.Image:
    """A dark obsidian layer whose alpha comes from alpha_at(x, y) on a coarse grid."""
    gw, gh = 64, 36
    mask = Image.new("L", (gw, gh))
    mask.putdata([max(0, min(255, int(alpha_at((x + 0.5) / gw, (y + 0.5) / gh))))
                  for y in range(gh) for x in range(gw)])
    layer = Image.new("RGBA", (w, h), OBSIDIAN + (0,))
    layer.putalpha(mask.resize((w, h), Image.BICUBIC))
    return layer


def _vignette(w: int, h: int, strength: int = 150) -> Image.Image:
    def alpha(x, y):
        d = ((x - 0.5) ** 2 / 0.25 + (y - 0.5) ** 2 / 0.25) ** 0.5
        return strength * max(0.0, d - 0.55) / 0.85
    return _shade(w, h, alpha)


def _grain(canvas: Image.Image, amount: int = 14) -> None:
    noise = Image.effect_noise(canvas.size, 40).convert("L")
    layer = Image.merge("RGBA", (noise, noise, noise, Image.new("L", canvas.size, amount)))
    canvas.alpha_composite(layer)


def _word(canvas: Image.Image, x: int, y: int, text: str, font, top_rgb, bottom_rgb,
          rng: random.Random, outline: int = 3, weathered: bool = True) -> None:
    """Text whose ink starts at (x, y): a vertical gradient fill, a thin dark
    outline, a soft drop shadow and a little stone wear."""
    box = font.getbbox(text)
    pad = max(12, outline * 4 + 10)
    w, h = box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - box[0], pad - box[1]), text, font=font, fill=255)

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(max(4, font.size // 18)))
                    .point(lambda v: int(v * 0.85)))
    off = max(3, font.size // 28)
    canvas.alpha_composite(shadow, (x - pad + off, y - pad + int(off * 1.4)))

    edge = mask.filter(ImageFilter.MaxFilter(outline * 2 + 1))
    rim = Image.new("RGBA", (w, h), OBSIDIAN + (0,))
    rim.putalpha(edge.point(lambda v: int(v * 0.9)))
    canvas.alpha_composite(rim, (x - pad, y - pad))

    fill = Image.new("RGB", (1, h))
    top_y, bottom_y = pad, h - pad
    for row in range(h):
        t = min(1.0, max(0.0, (row - top_y) / max(1, bottom_y - top_y)))
        fill.putpixel((0, row), tuple(int(a + (b - a) * t) for a, b in zip(top_rgb, bottom_rgb)))
    fill = fill.resize((w, h)).convert("RGBA")
    alpha = mask
    if weathered:
        # Fine pits and scratches, like letters cut in old stone or worn gold.
        wear = Image.effect_noise((max(1, w // 3), max(1, h // 3)), 70).resize((w, h), Image.BICUBIC)
        fill = Image.composite(fill, Image.new("RGBA", (w, h), SANDSTONE + (255,)),
                               wear.point(lambda v: 255 if v > 60 else 200))
        pits = Image.effect_noise((w, h), 70).point(lambda v: 0 if v > 250 - rng.randint(0, 3) else 255)
        alpha = Image.composite(mask, Image.new("L", (w, h), 0), pits)
    fill.putalpha(alpha)
    canvas.alpha_composite(fill, (x - pad, y - pad))


def _tracked_w(font, text: str, tracking: float) -> int:
    return int(sum(font.getlength(c) for c in text) + tracking * max(0, len(text) - 1))


def _tracked(canvas: Image.Image, x: int, y: int, text: str, font, fill, tracking: float) -> None:
    """Letter-spaced capitals whose ink starts at (x, y), with a soft shadow."""
    box = font.getbbox(text)
    pad = 20
    w, h = _tracked_w(font, text, tracking) + 2 * pad, box[3] - box[1] + 2 * pad
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    cx = pad
    for char in text:
        d.text((cx, pad - box[1]), char, font=font, fill=255)
        cx += font.getlength(char) + tracking
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.85)))
    canvas.alpha_composite(shadow, (x - pad + 2, y - pad + 3))
    layer = Image.new("RGBA", (w, h), tuple(fill) + (0,))
    layer.putalpha(mask)
    canvas.alpha_composite(layer, (x - pad, y - pad))


def _frame(canvas: Image.Image, inset: int, scale: float = 1.0) -> None:
    """A thin engraved double gold frame with bracketed corners and small diamonds."""
    w, h = canvas.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((inset, inset, w - inset, h - inset), outline=ANTIQUE_GOLD + (190,), width=max(2, int(2 * scale)))
    gap = int(7 * scale)
    d.rectangle((inset + gap, inset + gap, w - inset - gap, h - inset - gap), outline=ANTIQUE_GOLD + (110,), width=1)
    arm, thick = int(54 * scale), max(3, int(4 * scale))
    for cx, cy, sx, sy in ((inset, inset, 1, 1), (w - inset, inset, -1, 1),
                           (inset, h - inset, 1, -1), (w - inset, h - inset, -1, -1)):
        d.line([(cx, cy), (cx + sx * arm, cy)], fill=ROYAL_GOLD + (235,), width=thick)
        d.line([(cx, cy), (cx, cy + sy * arm)], fill=ROYAL_GOLD + (235,), width=thick)
        r = int(7 * scale)
        dx, dy = cx + sx * int(20 * scale), cy + sy * int(20 * scale)
        d.polygon([(dx, dy - r), (dx + r, dy), (dx, dy + r), (dx - r, dy)], fill=ROYAL_GOLD + (235,))
    canvas.alpha_composite(layer)


def _star(d: ImageDraw.ImageDraw, cx: float, cy: float, long: float, short: float,
          light, dark, turn: float = 0.0) -> None:
    """A bevelled compass star: each point is a light and a dark half."""
    for k in range(4):
        a = turn + k * math.pi / 2
        tip = (cx + long * math.cos(a), cy + long * math.sin(a))
        left = (cx + short * math.cos(a - math.pi / 4), cy + short * math.sin(a - math.pi / 4))
        right = (cx + short * math.cos(a + math.pi / 4), cy + short * math.sin(a + math.pi / 4))
        d.polygon([(cx, cy), left, tip], fill=light)
        d.polygon([(cx, cy), tip, right], fill=dark)


def _seal(size: int, rng: random.Random) -> Image.Image:
    """A dark-crimson wax seal pressed with a gold compass star."""
    s = size * 3
    c = s / 2
    r = s * 0.40
    blob = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(blob)
    pts, off = [], 0.0
    for i in range(72):
        off = max(-0.04, min(0.07, off + rng.uniform(-0.025, 0.025)))
        a = 2 * math.pi * i / 72
        pts.append((c + r * (1 + off) * math.cos(a), c + r * (1 + off) * math.sin(a)))
    d.polygon(pts, fill=255)
    for _ in range(3):  # little runs of wax at the edge
        a = rng.uniform(0, 2 * math.pi)
        br = s * rng.uniform(0.05, 0.08)
        bx, by = c + r * 1.02 * math.cos(a), c + r * 1.02 * math.sin(a)
        d.ellipse((bx - br, by - br, bx + br, by + br), fill=255)
    blob = blob.filter(ImageFilter.GaussianBlur(2))

    wax = Image.new("RGBA", (s, s), (92, 18, 20, 255))
    light = Image.new("L", (s, s), 0)
    ImageDraw.Draw(light).ellipse((c - r * 1.1, c - r * 1.15, c + r * 0.5, c + r * 0.45), fill=120)
    wax = Image.composite(Image.new("RGBA", (s, s), (150, 34, 32, 255)), wax,
                          light.filter(ImageFilter.GaussianBlur(s * 0.12)))
    d = ImageDraw.Draw(wax)
    ring = r * 0.74
    # The pressed rim: a dark groove with a light lip just inside it.
    d.ellipse((c - ring, c - ring, c + ring, c + ring), outline=(60, 10, 12, 255), width=int(s * 0.028))
    d.ellipse((c - ring + s * 0.02, c - ring + s * 0.02, c + ring - s * 0.01, c + ring - s * 0.01),
              outline=(168, 52, 46, 255), width=int(s * 0.012))
    _star(d, c, c, ring * 0.82, ring * 0.22, ROYAL_GOLD + (255,), ANTIQUE_GOLD + (255,))
    _star(d, c, c, ring * 0.48, ring * 0.14, ROYAL_GOLD + (255,), SANDSTONE + (255,), turn=math.pi / 4)
    d.ellipse((c - s * 0.025, c - s * 0.025, c + s * 0.025, c + s * 0.025), fill=(92, 18, 20, 255))
    grain = Image.effect_noise((s, s), 25).convert("L")
    wax = Image.composite(wax, Image.new("RGBA", (s, s), (70, 12, 14, 255)),
                          grain.point(lambda v: 255 if v > 60 else 200))
    wax.putalpha(blob)

    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    shadow.putalpha(blob.point(lambda v: int(v * 0.75)).filter(ImageFilter.GaussianBlur(s * 0.03)))
    out.alpha_composite(shadow, (int(s * 0.015), int(s * 0.03)))
    out.alpha_composite(wax)
    out = out.rotate(rng.uniform(-18, 18), resample=Image.BICUBIC)
    return out.resize((size, size), Image.LANCZOS)


def _strip(text: str, size: int) -> Image.Image:
    """The mystery warning strip: white Montserrat on dark crimson, a notched end."""
    font = _font("mont", size)
    tracking = size * 0.16
    tw, cap = _tracked_w(font, text, tracking), _cap_h(font)
    h = int(cap * 2.3)
    w = tw + int(size * 1.9)
    notch = int(h * 0.32)
    img = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shape = [(0, 0), (w, 0), (w - notch, h / 2), (w, h), (0, h)]
    d.polygon([(x + 5, y + 7) for x, y in shape], fill=(0, 0, 0, 150))
    img = img.filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(img)
    d.polygon(shape, fill=CRIMSON + (245,))
    d.line([(0, 3), (w - 3, 3)], fill=ANTIQUE_GOLD + (230,), width=2)
    d.line([(0, h - 3), (w - 3, h - 3)], fill=ANTIQUE_GOLD + (230,), width=2)
    _tracked(img, int(size * 0.7), (h - cap) // 2, text, font, IVORY, tracking)
    return img


def _wordmark(channel, height: int, rng: random.Random) -> Image.Image:
    """The logo file when there is one, else the name drawn as a gold wordmark
    on a crimson ribbon."""
    from .brand import logo as brand_logo

    logo_file = brand_logo(str(getattr(channel, "id", "") or "_"))
    if logo_file is not None:
        logo = Image.open(logo_file).convert("RGBA")
        return logo.resize((max(1, int(logo.width * height / logo.height)), height), Image.LANCZOS)
    name = str(getattr(channel, "brand", "") or getattr(channel, "name", "") or "PASTVEIL MYSTERIES").upper()
    first, _, rest = name.partition(" ")
    big = _font("cinzel", int(height * 0.42))
    small = _font("cinzel", int(height * 0.17))
    big_w = _ink_w(big, first)
    rest_w = _ink_w(small, rest) if rest else 0
    ribbon_w = max(rest_w + int(height * 0.5), int(big_w * 0.8))
    w = max(big_w, ribbon_w) + 40
    canvas = Image.new("RGBA", (w, height + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    cx = w // 2
    # A small gold compass point above the name.
    tip = int(height * 0.14)
    d.polygon([(cx, 2), (cx + tip * 0.3, tip), (cx, tip * 1.4), (cx - tip * 0.3, tip)], fill=ROYAL_GOLD + (255,))
    name_y = int(tip * 1.9)
    _word(canvas, cx - big_w // 2, name_y, first, big, ROYAL_GOLD, ANTIQUE_GOLD, rng, outline=2, weathered=False)
    if rest:
        ry = name_y + _cap_h(big) + int(height * 0.08)
        rh = int(_cap_h(small) * 2.0)
        x0, x1 = cx - ribbon_w // 2, cx + ribbon_w // 2
        d.polygon([(x0, ry), (x1, ry), (x1 - rh * 0.3, ry + rh / 2), (x1, ry + rh), (x0, ry + rh),
                   (x0 + rh * 0.3, ry + rh / 2)], fill=CRIMSON + (240,))
        d.line([(x0 + rh * 0.3, ry + 2), (x1 - rh * 0.3, ry + 2)], fill=ANTIQUE_GOLD + (255,), width=2)
        d.line([(x0 + rh * 0.3, ry + rh - 2), (x1 - rh * 0.3, ry + rh - 2)], fill=ANTIQUE_GOLD + (255,), width=2)
        box = small.getbbox(rest)
        d.text((cx - rest_w / 2 - box[0], ry + (rh - _cap_h(small)) / 2 - box[1]), rest, font=small,
               fill=IVORY + (255,))
    bbox = canvas.getbbox() or (0, 0, w, height)
    return canvas.crop(bbox)


def _wrap(text: str, font_name: str, max_w: int, hi: int, lo: int, max_lines: int):
    """(lines, font): the largest size at which `text` fits in max_lines lines."""
    words = text.split()
    for size in range(hi, lo - 1, -3):
        font = _font(font_name, size)
        lines, line = [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if _ink_w(font, trial) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        if len(lines) <= max_lines and all(_ink_w(font, x) <= max_w for x in lines):
            return lines, font
    return (lines or [text]), _font(font_name, lo)


def _headline(canvas: Image.Image, plan: dict, tag: str, x: int, y0: int, y1: int, column: int,
              sizes: tuple[int, int, int, int], rng: random.Random) -> None:
    """Left-aligned at x: the lead-in in letter-spaced gold, the key word in
    engraved Cinzel, a gold rule closed by a wax seal, then the crimson strip;
    the whole block centred vertically in [y0, y1]."""
    lead_size, big_hi, big_lo, strip_size = sizes
    lead = plan["top"]
    lead_font = _font("mont", lead_size)
    while lead and lead_font.size > 16 and _tracked_w(lead_font, lead, lead_font.size * 0.24) > column:
        lead_font = _font("mont", lead_font.size - 2)
    tracking = lead_font.size * 0.24
    big_lines, big_font = _wrap(plan["big"], "cinzel", int(column * 0.94), big_hi, big_lo, 2)
    lead_cap, big_cap = (_cap_h(lead_font) if lead else 0), _cap_h(big_font)
    strip = _strip(tag, strip_size)
    seal_size = int(big_cap * 1.15)
    gap_lead, gap_line, gap_rule = int(big_cap * 0.42), int(big_cap * 0.3), int(big_cap * 0.5)
    block = (((lead_cap + gap_lead) if lead else 0) + len(big_lines) * big_cap
             + (len(big_lines) - 1) * gap_line + gap_rule + seal_size // 2 + int(big_cap * 0.25) + strip.height)
    y = y0 + max(0, (y1 - y0 - block) // 2)
    if lead:
        _tracked(canvas, x + 2, y, lead, lead_font, ANTIQUE_GOLD, tracking)
        y += lead_cap + gap_lead
    widest = 0
    for line in big_lines:
        _word(canvas, x, y, line, big_font, ROYAL_GOLD, ANTIQUE_GOLD, rng, outline=3)
        widest = max(widest, _ink_w(big_font, line))
        y += big_cap + gap_line
    rule_y = y - gap_line + gap_rule
    end = x + max(widest, int(column * 0.55))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = max(5, big_cap // 12)
    d.polygon([(x + r, rule_y - r), (x + 2 * r, rule_y), (x + r, rule_y + r), (x, rule_y)], fill=ROYAL_GOLD + (255,))
    stop = end - seal_size // 2
    d.line([(x + 3 * r, rule_y), (stop, rule_y)], fill=ROYAL_GOLD + (255,), width=max(3, big_cap // 30))
    under = rule_y + max(6, big_cap // 14)
    d.line([(x + 3 * r, under), (stop, under)], fill=ANTIQUE_GOLD + (150,), width=1)
    canvas.alpha_composite(layer)
    seal = _seal(seal_size, rng)
    canvas.alpha_composite(seal, (min(stop, canvas.width - seal_size - 30), rule_y - seal_size // 2))
    canvas.alpha_composite(strip, (x, rule_y + seal_size // 2 + int(big_cap * 0.25)))


def _seed(plan: dict) -> random.Random:
    key = (plan.get("top", "") + plan.get("big", "")).encode("utf-8")
    return random.Random(int(hashlib.sha1(key).hexdigest(), 16))


def _base(visual: Path | None, w: int, h: int, focus_x: float) -> Image.Image:
    if visual is not None and Path(visual).is_file():
        art = Image.open(visual).convert("RGB")
        # The keyless image service stamps its name in the bottom corner.
        art = art.crop((0, 0, art.width, int(art.height * 0.93)))
        art = _grade(_cover(art, w, h, focus_x))
    else:
        # No picture at all: a navy-to-obsidian night sky with a warm horizon.
        art = Image.new("RGB", (1, 64))
        for row in range(64):
            t = row / 63
            col = NAVY if t < 0.6 else tuple(int(a + (b - a) * (t - 0.6) / 0.4) for a, b in zip(NAVY, SANDSTONE))
            art.putpixel((0, row), col)
        art = art.resize((w, h), Image.BICUBIC)
    return art.convert("RGBA")


# ------------------------------------------------------------------ the cards

def compose_long(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    w, h = 1280, 720
    rng = _seed(plan)
    canvas = _base(visual, w, h, 0.3)
    # The veil: a navy-black haze drawn in from the right over the picture.
    canvas.alpha_composite(_shade(w, h, lambda x, y: 220 * min(1, max(0, (x - 0.36) / 0.30))
                                  + 30 * max(0, 0.3 - y) / 0.3))
    canvas.alpha_composite(_vignette(w, h))
    _frame(canvas, 16)
    mark = _wordmark(channel, 108, rng)
    canvas.alpha_composite(mark, (w - mark.width - 46, 40))
    tag = plan.get("tag") or _TAGS[rng.randrange(len(_TAGS))]
    _headline(canvas, plan, tag, x=640, y0=40 + mark.height + 6, y1=h - 50, column=580,
              sizes=(30, 165, 70, 22), rng=rng)
    _grain(canvas)
    return _save(canvas, out)


def compose_short(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    # The Shorts shelf shows the middle of the card and crops ~8% off the top
    # and the bottom, so everything keeps 190px clear of both edges.
    w, h = 1080, 1920
    rng = _seed(plan)
    canvas = _base(visual, w, h, 0.5)
    canvas.alpha_composite(_shade(w, h, lambda x, y: 230 * min(1, max(0, (y - 0.45) / 0.2))
                                  + 150 * max(0, 0.2 - y) / 0.2))
    canvas.alpha_composite(_vignette(w, h, 120))
    _frame(canvas, 22, 1.4)
    # A small logo in the top-left corner, just inside the frame (your choice;
    # the Shorts shelf may trim a little off the top of the card).
    mark = _wordmark(channel, 112, rng)
    canvas.alpha_composite(mark, (64, 64))
    tag = plan.get("tag") or _TAGS[rng.randrange(len(_TAGS))]
    _headline(canvas, plan, tag, x=96, y0=1100, y1=h - 190, column=890,
              sizes=(44, 250, 100, 34), rng=rng)
    _grain(canvas)
    return _save(canvas, out)


def _save(canvas: Image.Image, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out


def render_visual(visual: str, out: Path, vertical: bool) -> Path | None:
    from .future_thumbnail import render_visual as render

    return render(visual, out, vertical, style=_STYLE, placement=_PLACE_SHORT if vertical else _PLACE_LONG,
                  stock_fallback="ancient ruins")


def compose_for_lesson(lesson, out: Path, channel, content_type: str = "long",
                       plan: dict | None = None, visual: Path | None = None) -> Path:
    """The whole card for one video: plan, picture, layout."""
    vertical = content_type == "short"
    if plan is None:
        from .brand import style_text

        try:
            plan = plan_for(lesson.title, style_text(str(getattr(channel, "id", "") or "_")), vertical)
        except Exception as exc:
            print(f"[mystery-thumb] headline writer unavailable ({str(exc)[:120]}); headline from the title")
            plan = fallback_plan(lesson.title, vertical)
    print(f"[mystery-thumb] {plan['top']} / {plan['big']} / {plan.get('tag', '')}")
    if visual is None:
        visual = render_visual(plan["visual"], out.with_name("thumbnail_visual.jpg"), vertical)
    if visual is None:
        print("[mystery-thumb] no picture could be made; the card is drawn on a night sky")
    return (compose_short if vertical else compose_long)(plan, visual, out, channel)
