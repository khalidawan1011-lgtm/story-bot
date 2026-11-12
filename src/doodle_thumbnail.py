"""Pondermals' thumbnail: a doodle-cartoon question card.

One hand-drawn doodle scene (thick black outlines, flat colours, a funny
animal with big eyes) fills the card; the question sits on top in chunky
yellow capitals with a thick black outline, readable at phone size. A small
white "PONDERMALS" tag with a paw sits bottom left (clear of YouTube's
duration badge). Shorts get a 1080x1920 card with the question inside the
area the Shorts shelf shows.

    channels.json: "thumbnail_style": "doodle"
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import settings

YELLOW = (255, 210, 31)
INK = (17, 17, 17)
PAPER = (250, 247, 238)
FONTS = settings.root / "fonts"

_STYLE = ("Simple hand-drawn doodle cartoon illustration, thick clean black outlines, flat bright colors, "
          "no shading, no gradients, expressive funny animal faces with big round white eyes, plain light "
          "background, like a webcomic. No text, no letters, no words, no speech bubbles, no watermark.")
_PLACE_LONG = (" Wide 16:9 composition: the animals large in the lower two thirds; the top quarter is plain "
               "empty light background.")
_PLACE_SHORT = (" Vertical 9:16 composition: the animals large in the middle and lower half; the top third is "
                "plain empty light background.")


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "ArchivoBlack-Regular.ttf"), max(8, int(size)))


def _ink_w(font, text: str) -> int:
    box = font.getbbox(text)
    return box[2] - box[0]


# ------------------------------------------------------------------ the plan

def plan_for(title: str, guide: str = "", vertical: bool = False) -> dict:
    """The question on the card and the doodle scene, written from the title."""
    from .genre_topics import _script_json

    guide_text = f"The channel's thumbnail style guide (follow it):\n{guide[:2000]}\n\n" if guide else ""
    plan = _script_json(
        guide_text
        + "Write the text for a funny doodle-cartoon YouTube thumbnail about an animal question.\n"
        f"Video title: {title}\n"
        'Return ONLY JSON: {"headline": str, "visual": str}.\n'
        f"- headline: {'2 to 4' if vertical else '3 to 5'} words, all capitals, a short punchy question or "
        "reaction that makes people curious (\"DO THEY LOVE US?\", \"WHY SO BORED?\", \"FISH SLEEP?!\"). "
        "Not the full title. Never claim more than the title does.\n"
        "- visual: one sentence describing ONE funny doodle scene that shows the question: which animal(s), "
        "what they are doing, their facial expression. Simple, readable at phone size. No text in it."
    )
    headline = re.sub(r"\s+", " ", str(plan.get("headline") or "")).strip().upper()[:40]
    if not headline:
        return fallback_plan(title, vertical)
    return {"headline": headline, "visual": str(plan.get("visual") or title).strip()[:400]}


def fallback_plan(title: str, vertical: bool = False) -> dict:
    clean = re.sub(r"\s*[|:–—]\s.*$", "", title).strip()
    words = clean.upper().split()
    headline = " ".join(words[: 4 if vertical else 5])
    if clean.endswith("?") and not headline.endswith("?"):
        headline += "?"
    return {"headline": headline, "visual": f"{clean}, a funny cartoon animal with big round eyes"}


# ------------------------------------------------------------------ drawing

def _cover(image: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / image.width, h / image.height)
    image = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))), Image.LANCZOS)
    left, top = (image.width - w) // 2, (image.height - h) // 2
    return image.crop((left, top, left + w, top + h))


def _wrap(text: str, max_w: int, hi: int, lo: int, max_lines: int):
    words = text.split()
    for size in range(hi, lo - 1, -4):
        font = _font(size)
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
    return lines, _font(lo)


def _headline(canvas: Image.Image, text: str, top: int, max_w: int, sizes: tuple[int, int], max_lines: int) -> int:
    """Yellow capitals with a thick black outline, centred; returns the bottom y."""
    lines, font = _wrap(text, max_w, sizes[0], sizes[1], max_lines)
    d = ImageDraw.Draw(canvas)
    stroke = max(6, font.size // 9)
    box = font.getbbox("H")
    cap = box[3] - box[1]
    y = top
    for line in lines:
        x = (canvas.width - _ink_w(font, line)) // 2 - font.getbbox(line)[0]
        # A drop shadow first, then the outlined letters.
        d.text((x + stroke // 2, y - box[1] + stroke), line, font=font, fill=INK, stroke_width=stroke, stroke_fill=INK)
        d.text((x, y - box[1]), line, font=font, fill=YELLOW, stroke_width=stroke, stroke_fill=INK)
        y += cap + int(cap * 0.32) + stroke
    return y


def _tag(canvas: Image.Image, channel, x: int, y_bottom: int, size: int) -> None:
    """A small white rounded tag: a paw and the channel name."""
    name = str(getattr(channel, "name", "") or "PONDERMALS").upper()
    font = _font(size)
    d = ImageDraw.Draw(canvas)
    paw = int(size * 1.1)
    w = paw + int(size * 0.6) + _ink_w(font, name) + int(size * 1.2)
    h = int(size * 1.9)
    y = y_bottom - h
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(255, 255, 255), outline=INK, width=max(3, size // 8))
    # The paw: one pad and four toes.
    cx, cy = x + int(size * 0.6) + paw // 2, y + h // 2 + int(size * 0.12)
    r = paw * 0.26
    d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 1.1), fill=INK)
    for dx, dy in ((-0.62, -0.62), (-0.22, -0.95), (0.22, -0.95), (0.62, -0.62)):
        tx, ty, tr = cx + dx * paw * 0.5, cy + dy * paw * 0.5, paw * 0.11
        d.ellipse((tx - tr, ty - tr, tx + tr, ty + tr), fill=INK)
    tb = font.getbbox(name)
    d.text((x + int(size * 0.6) + paw + int(size * 0.35) - tb[0], y + (h - (tb[3] - tb[1])) // 2 - tb[1]),
           name, font=font, fill=INK)


def _base(visual: Path | None, w: int, h: int) -> Image.Image:
    if visual is not None and Path(visual).is_file():
        return _cover(Image.open(visual).convert("RGB"), w, h).convert("RGBA")
    return Image.new("RGBA", (w, h), PAPER + (255,))


def compose_long(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    w, h = 1280, 720
    canvas = _base(visual, w, h)
    _headline(canvas, plan["headline"], 26, w - 90, (118, 64), 2)
    _tag(canvas, channel, 26, h - 24, 26)
    return _save(canvas, out)


def compose_short(plan: dict, visual: Path | None, out: Path, channel) -> Path:
    # The Shorts shelf trims about 8% off the top and the bottom.
    w, h = 1080, 1920
    canvas = _base(visual, w, h)
    _headline(canvas, plan["headline"], 230, w - 110, (170, 90), 3)
    tag_size = 36
    _tag(canvas, channel, (w - 0) // 2 - 200, h - 210, tag_size)
    return _save(canvas, out)


def _save(canvas: Image.Image, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out


def render_visual(visual: str, out: Path, vertical: bool) -> Path | None:
    from .future_thumbnail import render_visual as render

    return render(visual, out, vertical, style=_STYLE, placement=_PLACE_SHORT if vertical else _PLACE_LONG,
                  stock_fallback="cartoon animal",
                  # A real photo on a cartoon channel looks wrong: plain paper instead.
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
    return (compose_short if vertical else compose_long)(plan, visual, out, channel)
