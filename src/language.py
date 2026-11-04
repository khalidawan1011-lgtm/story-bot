"""Per-channel video language: English (default) or Urdu.

Urdu videos are written in Roman Urdu (Urdu in English letters, the way most
Pakistani viewers type and search), because that is what goes on screen and
into the title. The Urdu voice cannot read Roman Urdu, so the script also
carries every line in Urdu script as `speech`; only the voice hears that.
Scene labels and picture prompts stay in English, since the image models and
stock-footage search understand English.
"""
from __future__ import annotations

from pathlib import Path

LANGUAGES = {"en": "English", "ur": "Urdu (Roman Urdu on screen)"}

# Microsoft's Pakistani Urdu voices.
_URDU_MALE, _URDU_FEMALE = "ur-PK-AsadNeural", "ur-PK-UzmaNeural"
_FEMALE_HINTS = ("Aria", "Jenny", "Ava", "Emma", "Sonia", "Michelle", "Ana", "Uzma")


def channel_language(channel) -> str:
    value = str(getattr(channel, "language", "") or "en").lower()
    return value if value in LANGUAGES else "en"


def is_urdu(channel) -> bool:
    return channel_language(channel) == "ur"


def voice_for(channel, default: str | None = None) -> str | None:
    """The narrator voice: the channel's own, or the matching Urdu voice."""
    voice = getattr(channel, "voice", None) if channel is not None else None
    voice = voice or default
    if not is_urdu(channel):
        return voice
    if voice and voice.startswith("ur-"):
        return voice
    return _URDU_FEMALE if voice and any(h in voice for h in _FEMALE_HINTS) else _URDU_MALE


# Asked of every Urdu script and translation. Left alone, the writer mixes
# English into every sentence ("volunteer network ko fund kiya jata hai").
# Pushed the other way it wrote bookish Urdu nobody says aloud ("atiyaat",
# "sarbarah", "masnoi zehanat"), which the voice then read like a PTV bulletin.
# The aim is the Urdu a Karachi narrator actually speaks.
PURE_URDU = (
    "Write the everyday SPOKEN Urdu of Karachi, the way a good Pakistani YouTube narrator talks: "
    "warm, simple and natural, as if telling a friend. Short sentences.\n"
    "- Use the Urdu word people really say (madad, not help; zindagi, not life; dunya, not world; "
    "khatra, not danger; shuru, not start). Never use a heavy bookish word nobody says in conversation "
    "(say 'chanda' or 'donation', not 'atiyaat'; 'head', not 'sarbarah'; 'AI', not 'masnoi zehanat').\n"
    "- Words Pakistanis normally say in English stay English: AI, robot, computer, mobile, internet, "
    "technology, scientist, company, hospital, doctor, film, ambulance, and names of people, places and "
    "organisations. But the sentence itself is Urdu: never English verbs with 'karna' "
    "('fund kiya jata hai', 'develop kiya') where an Urdu verb exists.\n"
    "- It is Pakistani Urdu, so no Hindi words (waba, not mahamari; atiya, not daan; janaza for a funeral).\n"
)

# The Urdu-script 'speech' line is only ever heard, never seen, so it is written
# for the voice: Microsoft's Urdu voice guesses vowels Urdu script leaves out
# and reads کیا as "kya" where "kiya" was meant.
URDU_SPEECH_RULES = (
    "'speech' is read aloud by a text-to-speech voice, so write it for the ear:\n"
    "- Correct, standard Urdu spelling (Pakistani usage, Nastaliq letters, ے and ی in their right places).\n"
    "- Add zer/zabar/pesh ONLY on a word the voice could misread, e.g. کِیا for the verb 'kiya' "
    "(کیا alone means 'kya'), کُل vs کل, سُنا vs سنا. Do not add marks to every word.\n"
    "- English loanwords in their usual Urdu spelling (ٹیکنالوجی، روبوٹ، کمپیوٹر، انٹرنیٹ). "
    "Keep 'AI' as اے آئی.\n"
    "- Urdu punctuation for natural pauses: ، between clauses and ۔ at the end of each sentence.\n"
    "- Short sentences: at most about 15 words each; split a long one into two.\n"
    "- Write numbers as digits, the same as in 'line' (the voice turns them into words).\n"
)

# Numbers the voice is given as Urdu words, the way people say them:
# 1947 = انیس سو سینتالیس, 2050 = دو ہزار پچاس, 2.5 = ڈھائی, 1,50,000 = ڈیڑھ لاکھ.
_UR_0_99 = (
    "صفر ایک دو تین چار پانچ چھ سات آٹھ نو دس گیارہ بارہ تیرہ چودہ پندرہ سولہ سترہ اٹھارہ انیس "
    "بیس اکیس بائیس تئیس چوبیس پچیس چھبیس ستائیس اٹھائیس انتیس تیس اکتیس بتیس تینتیس چونتیس "
    "پینتیس چھتیس سینتیس اڑتیس انتالیس چالیس اکتالیس بیالیس تینتالیس چوالیس پینتالیس چھیالیس "
    "سینتالیس اڑتالیس انچاس پچاس اکاون باون تریپن چون پچپن چھپن ستاون اٹھاون انسٹھ ساٹھ اکسٹھ "
    "باسٹھ تریسٹھ چونسٹھ پینسٹھ چھیاسٹھ سڑسٹھ اڑسٹھ انہتر ستر اکہتر بہتر تہتر چوہتر پچہتر چھہتر "
    "ستتر اٹھہتر اناسی اسی اکیاسی بیاسی تراسی چوراسی پچاسی چھیاسی ستاسی اٹھاسی نواسی نوے اکانوے "
    "بانوے ترانوے چورانوے پچانوے چھیانوے ستانوے اٹھانوے ننانوے"
).split()
_UR_SCALES = ((10**9, "ارب"), (10**7, "کروڑ"), (10**5, "لاکھ"), (1000, "ہزار"), (100, "سو"))


def urdu_number(n: int) -> str:
    """A whole number in Urdu words. 1100-1999 are said in hundreds
    (انیس سو سینتالیس), as Urdu does for years and counts alike."""
    if n < 100:
        return _UR_0_99[n]
    if 1100 <= n < 2000:
        rest = n % 100
        return f"{_UR_0_99[n // 100]} سو" + (f" {_UR_0_99[rest]}" if rest else "")
    parts = []
    for size, word in _UR_SCALES:
        if n >= size:
            parts.append(f"{urdu_number(n // size)} {word}")
            n %= size
    if n:
        parts.append(_UR_0_99[n])
    return " ".join(parts)


def _urdu_decimal(whole: int, frac: str) -> str:
    if frac == "5":
        if whole == 1:
            return "ڈیڑھ"
        if whole == 2:
            return "ڈھائی"
        if whole < 100:
            return f"ساڑھے {urdu_number(whole)}"
    return f"{urdu_number(whole)} اعشاریہ " + " ".join(_UR_0_99[int(d)] for d in frac)


def urdu_numbers_to_words(text: str) -> str:
    import re

    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    # 2030-2040 = 2030 سے 2040
    text = re.sub(r"(\d)\s*[-–]\s*(\d)", r"\1 سے \2", text)

    def say(match: re.Match) -> str:
        whole, frac, pct = match.group(1).replace(",", ""), match.group(2), match.group(3)
        if len(whole) > 12:
            return match.group(0)
        words = _urdu_decimal(int(whole), frac) if frac else urdu_number(int(whole))
        return words + (" فیصد" if pct else "")

    return re.sub(r"(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?(?:\s*(%))?", say, text)

# Fixes applied to every Urdu line just before the voice reads it, for words
# the voice keeps getting wrong. data/urdu_pronunciation.json can add more:
# {"written": "how the voice should read it"}.
_URDU_SAY_FIXES = {
    "کیا گیا": "کِیا گیا",
    "کیا گئی": "کِیا گئی",
    "کیا گئے": "کِیا گئے",
    "کیا جاتا": "کِیا جاتا",
    "کیا جاتی": "کِیا جاتی",
    "کیا جاتے": "کِیا جاتے",
    "کیا جا سکتا": "کِیا جا سکتا",
    "کیا جا سکتی": "کِیا جا سکتی",
    "کیا جائے": "کِیا جائے",
    "کیا جائےگا": "کِیا جائےگا",
}


def urdu_for_voice(text: str) -> str:
    """The Urdu line with known misread words respelled for the voice."""
    import json

    from .config import ROOT

    fixes = dict(_URDU_SAY_FIXES)
    extra = Path(ROOT) / "data" / "urdu_pronunciation.json"
    try:
        fixes.update({str(k): str(v) for k, v in json.loads(extra.read_text(encoding="utf-8")).items()
                      if not str(k).startswith("_")})
    except (OSError, ValueError, AttributeError):
        pass
    for written in sorted(fixes, key=len, reverse=True):
        text = text.replace(written, fixes[written])
    text = urdu_numbers_to_words(text)
    # The voice pauses on Urdu punctuation; English commas it rushes. A comma
    # inside a number (1,000) is left alone.
    import re

    text = re.sub(r"(?<!\d),|,(?!\d)", "،", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", "۔", text)
    return text.replace("?", "؟")


# Viewers stay to the end when a question is left open: the hook makes them
# ask it, and the answer is held back until the last scenes.
STORY_ARC = (
    "\nSTORY SHAPE (a documentary told as a mystery, not a list of facts):\n"
    "- HOOK: the first line is the single most astonishing fact or moment, told so the viewer "
    "has to know more: a real date, size, number or discovery about THIS subject, in your own "
    "words. Never a stock line that could open any video.\n"
    "- QUESTION: right after it, ask the one question this video will answer "
    "(why, how, what really happened).\n"
    "- CLUES: then tell it step by step; each line adds a clue and leaves something open for the next.\n"
    "- ANSWER: give the full answer near the end, then close with one line that leaves the viewer in awe.\n"
    "- Every clue and the answer must still be facts allowed by the rules above.\n"
    "- Name the exact subject (the person, animal, place, planet or event) in the first two lines, "
    "and give real details: names, places, dates, sizes, numbers. Never stay vague "
    "(\"an ancient predator\", \"researchers found\") where a name exists.\n"
    "- The video must feel finished: the last lines state the answer and what it means. Never end "
    "on an open question or a teaser, and never claim more than is known.\n"
)


# Money videos teach; a script telling a viewer what to buy is advice YouTube
# treats as harmful when it is wrong, and no script can know the viewer.
FINANCE_RULES = (
    "\nMONEY RULES (personal finance channel):\n"
    "- Explain how things work; never tell the viewer to buy, sell or avoid a specific stock, fund, "
    "coin, bank, card or product, and never name one as a recommendation.\n"
    "- No promises or predictions of returns, no 'get rich', no 'guaranteed'.\n"
    "- Say 'for example' when a number is an illustration, and keep every real figure as the source "
    "gives it.\n"
    "- The title speaks to the viewer's own money (e.g. 'How Compound Interest Quietly Builds "
    "Wealth', 'Credit Scores Explained'), not to a historical figure in the article.\n"
)


# Future-science videos talk about years that have not happened yet; a script
# that says "by 2035 scientists discovered" presents a guess as history.
FUTURE_RULES = (
    "\nFUTURE SCIENCE RULES (future technology channel):\n"
    "- The topic is technology, AI, robotics, biotechnology, energy, space or future cities. "
    "Not deep-sea, ancient-Earth or wildlife mysteries.\n"
    "- Today is " + __import__("datetime").date.today().strftime("%B %Y") + ". Anything after "
    "today is a possibility: write 'could', 'might', 'researchers expect'. Never use past tense "
    "for a future year, and never say a future event was discovered or happened.\n"
    "- Build each video in three clear layers: what exists today, what researchers are testing now "
    "(with its limits), and what might come later (labelled as a scenario).\n"
    "- Use only real, well-known technologies, organisations and results. Never invent a study, a "
    "quote, a percentage or a named scientist; when unsure, stay general.\n"
    "- The title is a question or a scenario (e.g. 'Could Robots Run Entire Cities?'), never a "
    "claim that a future thing is certain.\n"
)


def script_rules(channel) -> str:
    """Extra instructions for the script writer: the story shape (every channel
    but the preschool one), and the language rules on an Urdu one."""
    wanted = getattr(channel, "story_arc", True) and not getattr(channel, "builtin", False)
    story = STORY_ARC if wanted else ""
    genre = str(getattr(channel, "genre", "") or "").lower()
    if "finance" in genre:
        story += FINANCE_RULES
    if "future" in genre:
        story += FUTURE_RULES
    if not is_urdu(channel):
        return story
    return story + (
        "\nLANGUAGE: this channel publishes in URDU for a Pakistani audience.\n"
        "- 'line' = the narrated sentence(s) in ROMAN URDU: Urdu written in English letters, "
        "the way people type on WhatsApp (e.g. \"Yeh kahani ek purani haveli se shuru hoti hai.\"). "
        "Natural everyday Urdu, not word-by-word translated English.\n"
        "- 'speech' = exactly the same text as 'line', written in Urdu script (اردو), for the narrator's voice.\n"
        "- 'title', 'intro' and 'outro' in Roman Urdu; the title may add one or two English search words.\n"
        "- Keep 'label' and 'image_prompt' in ENGLISH.\n"
        "- Word counts asked for above apply to 'line'.\n"
        "- " + PURE_URDU + URDU_SPEECH_RULES
    )


def display_marks(marks, display_text: str):
    """Karaoke timings for the on-screen words when the voice read other words.

    The voice speaks Urdu script but the caption shows Roman Urdu, so the word
    lists differ. The spoken span is kept and the shown words are spread over
    it by length, which tracks the voice closely enough for a highlight.
    """
    from .tts import _split_boundary_into_words

    if not marks:
        return marks
    start = marks[0][1]
    end = max(s + d for _w, s, d in marks)
    return _split_boundary_into_words(display_text, start, max(0.1, end - start))
