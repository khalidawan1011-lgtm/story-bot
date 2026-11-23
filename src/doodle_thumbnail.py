"""Pondermals' thumbnails: one hand-drawn doodle brand, two layouts.

Fixed palette: Yellow #FFC928, Navy #10385B, Cream #FFF7E7, Coral #FF7665,
Green #8FCB76. Every card is one expressive doodle animal (cut out of its
generated picture and set on a flat brand colour), a short question, doodled
question marks and the Pondermals paw logo. Only the animal, the headline and
the little mystery visual change from video to video.

Short (1080x1920), "bold, funny & curious": bright yellow, cream or light
blue; the animal large and close; 2-4 words on top in navy capitals with a
white outline, the key word in white; logo small at the bottom, everything
inside the area the Shorts shelf shows.

Long (1280x720), "mystery + science + storytelling": cream with a navy panel
on the right; the animal large on the left, breaking into the panel; 3-5
words on the navy, the key word on a yellow marker stroke; logo top left
(the duration badge covers the bottom right).

The headline marks its key word(s) with *stars*. A logo with real
transparency at data/brand/pondermals/logo.png replaces the drawn paw tag.

    channels.json: "thumbnail_style": "doodle"
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import settings

YELLOW = (255, 201, 40)
NAVY = (16, 56, 91)
CREAM = (255, 247, 231)
CORAL = (255, 118, 101)
GREEN = (143, 203, 118)
WHITE = (255, 255, 255)
LIGHT_BLUE = (214, 236, 250)   # the spec's third Shorts background
FONTS = settings.root / "fonts"

_STYLE = ("Simple hand-drawn doodle cartoon illustration, thick clean black outlines, flat bright colors, "
          "no shading, no gradients, ONE expressive funny animal with big round white eyes, on a plain "
          "white background with nothing else, like a webcomic sticker. No text, no letters, no words, "
          "no speech bubbles, no question marks, no watermark.")
_PLACE_LONG = " The animal large and centred, its whole head and body visible, plain white around it."
_PLACE_SHORT = " Vertical 9:16 close-up: the animal's head and upper body large, plain white around it."


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "ArchivoBlack-Regular.ttf"), max(8, int(size)))


def _ink_w(font, text: str) -> int:
    box = font.getbbox(text)
    return box[2] - box[0]


def _cap(font) -> int:
    box = font.getbbox("H")
    return box[3] - box[1]


# ------------------------------------------------------------------ the plan

def plan_for(title: str, guide: str = "", vertical: bool = False) -> dict:
    """The question on the card and the doodle animal, written from the title."""
    from .genre_topics import _script_json

    guide_text = f"The channel's thumbnail style guide (follow it):\n{guide[:2500]}\n\n" if guide else ""
    examples = ('"*CATS* DREAM?!", "FISH *SLEEP*?!"' if vertical
                else '"DO *CATS* LOVE US?", "WHY DO DOGS *TILT*?"')
    plan = _script_json(
        guide_text
        + "Write the text for a doodle-cartoon YouTube thumbnail about an animal question.\n"
        f"Video title: {title}\n"
        'Return ONLY JSON: {"headline": str, "visual": str}.\n'
        f"- headline: {'2 to 4' if vertical else '3 to 5'} words, all capitals, a punchy question that makes "
        "people curious, with the ONE key word (usually the animal or the surprising verb) wrapped in *stars* "
        f"({examples}). "
        "Not the full title. Never claim more than the title does.\n"
        "- visual: one sentence describing ONE doodle animal that shows the question: which animal, what it "
        "is doing or holding, and a strong facial expression (surprised, puzzled, guilty, dreamy). One animal "
        "only, no background scene, no text."
    )
    headline = re.sub(r"\s+", " ", str(plan.get("headline") or "")).strip().upper()[:44]
    if not headline.replace("*", "").strip():
        return fallback_plan(title, vertical)
    return {"headline": headline, "visual": str(plan.get("visual") or title).strip()[:400]}


_SKIP = {"THE", "A", "AN", "OF", "DO", "DOES", "CAN", "WHY", "WHAT", "HOW", "IS", "ARE", "EVER", "REALLY"}


def fallback_plan(title: str, vertical: bool = False) -> dict:
    clean = re.sub(r"\s*[|:–—]\s.*$", "", title).strip()
    words = clean.upper().replace("?", "").split()[: 4 if vertical else 5]
    key = next((i for i, w in enumerate(words) if w not in _SKIP), 0) if words else 0
    if words:
        words[key] = f"*{words[key]}*"
    headline = " ".join(words) + ("?" if clean.endswith("?") else "")
    return {"headline": headline or "*ANIMALS*?", "visual": f"{clean}, one funny doodle animal with big round eyes"}


def _words(headline: str) -> list[tuple[str, bool]]:
    """[(word, is_key)], the *starred* words being the key ones."""
    out, key = [], False
    for token in headline.split():
        starts, ends = token.startswith("*"), token.rstrip("?!.,").endswith("*")
        key = key or starts
        word = token.replace("*", "")
        if word:
            out.append((word, key))
        if ends:
            key = False
    if out and not any(k for _, k in out):
        # No key word marked: the longest one carries the colour.
        i = max(range(len(out)), key=lambda n: len(out[n][0].strip("?!")))
        out[i] = (out[i][0], True)
    return out


# ------------------------------------------------------------------ drawing pieces

def _lines(words: list[tuple[str, bool]], max_w: int, hi: int, lo: int, max_lines: int):
    """Wrap word by word: ([[(word, key)], ...], font) at the largest size that fits."""
    for size in range(hi, lo - 1, -4):
        font = _font(size)
        space = _ink_w(font, "H") * 0.35
        lines, line, width = [], [], 0.0
        for word, key in words:
            w = _ink_w(font, word)
            if line and width + space + w > max_w:
                lines.append(line)
                line, width = [], 0.0
            width += (space if line else 0) + w
            line.append((word, key))
        if line:
            lines.append(line)
        if len(lines) <= max_lines and all(
                sum(_ink_w(font, w) for w, _ in ln) + space * (len(ln) - 1) <= max_w for ln in lines):
            return lines, font
    return lines, _font(lo)


def _draw_lines(canvas: Image.Image, lines, font, x0: int, top: int, max_w: int, align: str,
                plain_fill, plain_stroke, key_fill, key_stroke, marker=None) -> int:
    """Outlined words, line by line; returns the bottom y. `marker` paints a
    yellow marker stroke behind the key words (long card)."""
    d = ImageDraw.Draw(canvas)
    stroke = max(5, font.size // 10)
    cap = _cap(font)
    space = _ink_w(font, "H") * 0.35
    y = top
    for line in lines:
        width = sum(_ink_w(font, w) for w, _ in line) + space * (len(line) - 1)
        x = x0 + (max_w - width) / 2 if align == "center" else x0
        for word, key in line:
            w = _ink_w(font, word)
            oy = y - font.getbbox(word)[1]
            if key and marker:
                pad = cap * 0.22
                d.rounded_rectangle((x - pad, y - pad * 0.9, x + w + pad, y + cap + pad * 1.1),
                                    radius=int(pad), fill=marker)
            fill, outline = (key_fill, key_stroke) if key else (plain_fill, plain_stroke)
            ox = x - font.getbbox(word)[0]
            if outline:
                d.text((ox + stroke * 0.5, oy + stroke * 0.8), word, font=font, fill=NAVY,
                       stroke_width=stroke, stroke_fill=NAVY)
                d.text((ox, oy), word, font=font, fill=fill, stroke_width=stroke, stroke_fill=outline)
            else:
                d.text((ox, oy), word, font=font, fill=fill)
            x += w + space
        y += cap + int(cap * 0.42) + (stroke if plain_stroke else 0)
    return y


def _question_mark(size: int, color, angle: float) -> Image.Image:
    """A doodled question mark: brand colour, navy outline, a little tilt."""
    font = _font(size)
    box = font.getbbox("?")
    stroke = max(4, size // 12)
    w, h = box[2] - box[0] + 4 * stroke, box[3] - box[1] + 4 * stroke
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 * stroke - box[0], 2 * stroke - box[1]), "?", font=font, fill=color,
                             stroke_width=stroke, stroke_fill=NAVY)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True)


def _clean_logo(logo: Image.Image) -> Image.Image:
    """The logo without hairlines left in the file (a 1-3 px stray line above it)
    and without its empty margin. Pieces thinner than 6% of the logo, measured
    after a light erosion, are dropped."""
    try:
        import cv2
        import numpy as np

        alpha = np.array(logo.getchannel("A"))
        solid = (alpha > 20).astype(np.uint8)
        # Erode 1 px: a hairline vanishes, real shapes only shrink a little.
        core = cv2.erode(solid, np.ones((3, 3), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
        tall = max(1, int(logo.height * 0.06))
        keep_core = np.zeros_like(core)
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_HEIGHT] >= tall:
                keep_core[labels == i] = 1
        # Grow the kept shapes back and cut everything else away.
        keep = cv2.dilate(keep_core, np.ones((5, 5), np.uint8)) & solid
        if keep.any():
            cleaned = np.array(logo)
            cleaned[..., 3] = np.where(keep > 0, alpha, 0)
            logo = Image.fromarray(cleaned, "RGBA")
    except Exception as exc:
        print(f"[doodle-thumb] logo kept as it is: {exc}")
    bbox = logo.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    return logo.crop(bbox) if bbox else logo


def _logo(channel, height: int, on_dark: bool) -> Image.Image:
    """The logo file when there is one, else the paw tag: a pill with a paw and
    the name (navy on light cards, cream on the navy panel)."""
    from .brand import logo as brand_logo

    logo_file = brand_logo(str(getattr(channel, "id", "") or "_"))
    if logo_file is not None:
        logo = Image.open(logo_file).convert("RGBA")
        logo = _clean_logo(logo)
        logo = logo.resize((max(1, int(logo.width * height / logo.height)), height), Image.LANCZOS)
        # A white sticker edge, so the yellow underline still reads on yellow.
        edge = max(3, height // 22)
        sticker = Image.new("RGBA", (logo.width + 2 * edge, logo.height + 2 * edge), (0, 0, 0, 0))
        grown = Image.new("L", sticker.size, 0)
        grown.paste(logo.getchannel("A"), (edge, edge))
        grown = grown.filter(ImageFilter.MaxFilter(2 * edge + 1)).filter(ImageFilter.GaussianBlur(1))
        white = Image.new("RGBA", sticker.size, WHITE + (255,))
        white.putalpha(grown)
        sticker.alpha_composite(white)
        sticker.alpha_composite(logo, (edge, edge))
        return sticker
    name = str(getattr(channel, "name", "") or "PONDERMALS").upper()
    size = int(height * 0.48)
    font = _font(size)
    paw = int(height * 0.62)
    pad = int(height * 0.32)
    w = pad + paw + int(height * 0.18) + _ink_w(font, name) + pad
    img = Image.new("RGBA", (w + 6, height + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg, fg = (NAVY, CREAM) if not on_dark else (CREAM, NAVY)
    d.rounded_rectangle((3, 3, w + 3, height + 3), radius=(height + 6) // 2, fill=bg)
    cx, cy = 3 + pad + paw / 2, 3 + height / 2 + paw * 0.1
    r = paw * 0.27
    d.ellipse((cx - r, cy - r * 0.55, cx + r, cy + r * 1.05), fill=YELLOW)
    for dx, dy in ((-0.66, -0.55), (-0.24, -0.92), (0.24, -0.92), (0.66, -0.55)):
        tx, ty, tr = cx + dx * paw * 0.5, cy + dy * paw * 0.5, paw * 0.12
        d.ellipse((tx - tr, ty - tr, tx + tr, ty + tr), fill=YELLOW)
    tb = font.getbbox(name)
    d.text((3 + pad + paw + int(height * 0.18) - tb[0], 3 + (height - (tb[3] - tb[1])) / 2 - tb[1]),
           name, font=font, fill=fg)
    return img


def _lift_off_white(img: Image.Image) -> Image.Image | None:
    """The doodle without its plain light background: flood the background in
    from the edges (a doodle's thick black outline stops the flood), make it
    transparent and crop to the drawing. None when the picture has no plain
    background to flood (a full scene), so the caller can try rembg."""
    small = img.copy()
    small.thumbnail((640, 640))
    marker = (255, 0, 255)
    # A white frame round the picture lets one flood reach every bit of the
    # background, edge strips included.
    pad = 6
    w0, h0 = small.size
    work = Image.new("RGB", (w0 + 2 * pad, h0 + 2 * pad), (255, 255, 255))
    work.paste(small, (pad, pad))
    ImageDraw.floodfill(work, (0, 0), marker, thresh=42)
    work = work.crop((pad, pad, pad + w0, pad + h0))
    w, h = work.size
    mask = Image.new("L", (w, h), 0)
    mask.putdata([0 if p == marker else 255 for p in work.getdata()])
    kept = sum(1 for v in mask.resize((64, 64)).getdata() if v > 128) / 4096
    if not 0.05 < kept < 0.80:
        return None
    # Soften the cut edge a touch, then scale the mask back to full size.
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8)).resize(img.size, Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(mask)
    bbox = mask.point(lambda v: 255 if v > 60 else 0).getbbox()
    return out.crop(bbox) if bbox else None


def _animal(visual: Path | None, work: Path) -> Image.Image | None:
    """The doodle animal on transparency (cut out of its white background), or
    the whole picture when it cannot be cut out cleanly."""
    if visual is None or not Path(visual).is_file():
        return None
    lifted = _lift_off_white(Image.open(visual).convert("RGB"))
    if lifted is not None:
        return lifted
    try:
        from .story_thumbnail import _cutout

        cut = _cutout(Path(visual), work / "thumbnail_animal.png")
        if cut:
            img = Image.open(cut).convert("RGBA")
            alpha = img.getchannel("A")
            share = sum(1 for v in alpha.resize((64, 64)).getdata() if v > 128) / 4096
            bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
            if bbox and 0.05 < share < 0.85:
                return img.crop(bbox)
    except Exception as exc:
        print(f"[doodle-thumb] no cut-out ({exc}); using the whole picture")
    img = Image.open(visual).convert("RGBA")
    # Fade the picture's own white into the card: a soft rounded mask.
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width, img.height), radius=img.width // 12, fill=255)
    img.putalpha(mask)
    return img


def _place(canvas: Image.Image, animal: Image.Image, box: tuple[int, int, int, int], anchor: str) -> tuple:
    """Fit the animal inside box (x0, y0, x1, y1), with a soft navy drop shadow;
    returns its (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    scale = min((x1 - x0) / animal.width, (y1 - y0) / animal.height)
    a = animal.resize((max(1, int(animal.width * scale)), max(1, int(animal.height * scale))), Image.LANCZOS)
    x = x0 + ((x1 - x0) - a.width) // 2
    y = y1 - a.height if anchor == "bottom" else y0 + ((y1 - y0) - a.height) // 2
    shadow = Image.new("RGBA", a.size, NAVY + (0,))
    shadow.putalpha(a.getchannel("A").point(lambda v: int(v * 0.28)).filter(ImageFilter.GaussianBlur(10)))
    canvas.alpha_composite(shadow, (x + 10, y + 14))
    canvas.alpha_composite(a, (x, y))
    return x, y, x + a.width, y + a.height


def _sprinkle(canvas: Image.Image, area: tuple, rng: random.Random, sizes: tuple[int, int], count: int,
             x_max: int | None = None) -> None:
    """Doodled coral and green question marks beside the animal's head, kept
    left of x_max (the long card's text panel)."""
    x0, y0, x1, y1 = area
    right_edge = (x_max if x_max is not None else canvas.width) - 10
    for i in range(count):
        mark = _question_mark(rng.randint(*sizes), (CORAL, GREEN)[i % 2], rng.uniform(-24, 24))
        x = int(x0 - mark.width * 0.55) if i % 2 == 0 else int(x1 - mark.width * 0.45)
        y = int(y0 - mark.height * 0.2 + (y1 - y0) * rng.uniform(0.0, 0.25))
        x = max(10, min(right_edge - mark.width, x))
        canvas.alpha_composite(mark, (x, max(10, y)))


def _background_for(animal: Image.Image | None, rng: random.Random):
    """Yellow, cream or light blue: whichever stands furthest from the animal's
    own colour (a yellow fish never sits on yellow); ties go by the headline."""
    choices = [YELLOW, CREAM, LIGHT_BLUE]
    if animal is None:
        return choices[rng.randrange(3)]
    small = animal.copy()
    small.thumbnail((64, 64))
    pixels = [p[:3] for p in small.getdata() if p[3] > 128 and sum(p[:3]) > 120]  # skip the black outline
    if not pixels:
        return choices[rng.randrange(3)]
    mean = tuple(sum(c[i] for c in pixels) / len(pixels) for i in range(3))
    distance = lambda c: sum((a - b) ** 2 for a, b in zip(c, mean))  # noqa: E731
    best = max(distance(c) for c in choices)
    close = [c for c in choices if distance(c) >= best * 0.8]
    return close[rng.randrange(len(close))]


def _rng(headline: str) -> random.Random:
    return random.Random(int(hashlib.sha1(headline.encode("utf-8")).hexdigest(), 16))


def _wobbly_panel(w: int, h: int, x_edge: int, rng: random.Random) -> Image.Image:
    """The navy panel on the right, its left edge a hand-drawn wobble."""
    mask = Image.new("L", (w, h), 0)
    pts = [(w, 0)]
    phase = rng.uniform(0, math.pi * 2)
    for y in range(0, h + 1, 12):
        pts.append((x_edge + 14 * math.sin(y / 70 + phase) + rng.uniform(-3, 3), y))
    pts.append((w, h))
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    panel = Image.new("RGBA", (w, h), NAVY + (255,))
    panel.putalpha(mask)
    return panel


# ------------------------------------------------------------------ the cards

def compose_long(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    w, h = 1280, 720
    rng = _rng(plan["headline"])
    canvas = Image.new("RGBA", (w, h), CREAM + (255,))
    panel_x = 600
    canvas.alpha_composite(_wobbly_panel(w, h, panel_x, rng))
    animal = _animal(visual, out.parent)
    if animal is not None:
        spot = _place(canvas, animal, (40, 120, panel_x + 70, h - 22), "bottom")
        _sprinkle(canvas, spot, rng, (70, 96), 2, x_max=panel_x - 20)
    logo = _logo(channel, 84, on_dark=False)
    canvas.alpha_composite(logo, (22, 18))
    lines, font = _lines(_words(plan["headline"]), w - panel_x - 110, 104, 50, 4)
    cap = _cap(font)
    block = len(lines) * cap + (len(lines) - 1) * int(cap * 0.42)
    top = max(40, (h - block) // 2)
    _draw_lines(canvas, lines, font, panel_x + 60, top, w - panel_x - 110, "left",
                CREAM, None, NAVY, None, marker=YELLOW)
    return _save(canvas, out)


def compose_short(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    # The Shorts shelf trims about 8% off the top and the bottom: 190 px clear.
    w, h = 1080, 1920
    rng = _rng(plan["headline"])
    animal = _animal(visual, out.parent)
    bg = _background_for(animal, rng)
    canvas = Image.new("RGBA", (w, h), bg + (255,))
    # A soft lighter halo behind the animal so it pops off the flat colour.
    halo = Image.new("L", (w, h), 0)
    ImageDraw.Draw(halo).ellipse((90, 760, w - 90, 1640), fill=110)
    glow = Image.new("RGBA", (w, h), WHITE + (255,))
    glow.putalpha(halo.filter(ImageFilter.GaussianBlur(60)))
    canvas.alpha_composite(glow)
    lines, font = _lines(_words(plan["headline"]), w - 120, 190, 96, 3)
    bottom = _draw_lines(canvas, lines, font, 60, 230, w - 120, "center",
                         NAVY, WHITE, WHITE, NAVY)
    logo = _logo(channel, 130, on_dark=False)
    logo_y = h - 190 - logo.height
    if animal is not None:
        spot = _place(canvas, animal, (40, bottom + 30, w - 40, logo_y - 30), "bottom")
        _sprinkle(canvas, spot, rng, (110, 150), 3)
    canvas.alpha_composite(logo, ((w - logo.width) // 2, logo_y))
    return _save(canvas, out)


def _save(canvas: Image.Image, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out


def render_visual(visual: str, out: Path, vertical: bool) -> Path | None:
    from .future_thumbnail import render_visual as render

    return render(visual, out, vertical, style=_STYLE, placement=_PLACE_SHORT if vertical else _PLACE_LONG,
                  stock_fallback="cartoon animal",
                  # A real photo on a cartoon channel looks wrong: the card is drawn without one.
                  stock=False)


def compose_for_lesson(lesson, out: Path, channel, content_type: str = "long",
                       plan: dict | None = None, visual: Path | None = None) -> Path:
    vertical = content_type == "short"
    if plan is None:
        from .brand import style_text

        try:
            plan = plan_for(lesson.title, style_text(str(getattr(channel, "id", "") or "_")), vertical)
        except Exception as exc:
            print(f"[doodle-thumb] headline writer unavailable ({str(exc)[:120]}); headline from the title")
            plan = fallback_plan(lesson.title, vertical)
    print(f"[doodle-thumb] {plan['headline']}")
    if visual is None:
        visual = render_visual(plan["visual"], out.with_name("thumbnail_visual.jpg"), vertical)
    if visual is None:
        # A card with only the headline went up on Sea Otters and Elephants.
        from .thumbnail_check import ThumbnailNotReady

        raise ThumbnailNotReady("no picture could be made (the image services are out of quota or down); the video waits and its thumbnail is made again on a later run")
    return (compose_short if vertical else compose_long)(plan, visual, out, channel)
