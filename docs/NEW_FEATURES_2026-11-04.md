# New features — 4 Nov 2026

Everything added to Story Bot Studio today, with the files involved and a
copy-paste prompt for adding the same feature to another bot.

## How to move these features to another bot

**If the other bot is a copy of this same Story Bot** (same `src/` files), the
fastest and safest way is to copy the code, not to rebuild it:

```
# in the OTHER bot's folder
git remote add chrono https://github.com/worldvalorchronicles-ui/story-bot.git
git fetch chrono
git cherry-pick 3c7d49e 5f121ac 53d3711 8ae0698 26cfa19 8475fde 38d0ec7 0035e0f 6ac16c5 ef8f1c5 9309e06
```

Skip the Chronovanta-only commits (a93e520, 31a42d0, cab0ebe): they hold this
channel's settings. If a cherry-pick conflicts, give the prompt of that
feature (below) to Claude Code in the other bot instead.

**If the other bot is different**, open Claude Code in it and paste the
prompt of the feature you want. Each prompt is self-contained.

| # | Feature | Main files |
|---|---|---|
| 1 | No video uploads without a verified thumbnail | `src/thumbnail_check.py`, `src/youtube_upload.py`, `src/pipeline.py`, `src/pending_uploads.py` |
| 2 | Per-platform upload times + thumbnail on every video (dashboard and status page) | `src/platform_times.py`, `web_dashboard.py`, `scripts/build_status_page.py`, `src/db.py`, `src/social_publish.py` |
| 3 | Daily YouTube thumbnail audit (auto-fix missing thumbnails) | `src/thumbnail_audit.py`, `src/cli.py`, `.github/workflows/daily-videos.yml` |
| 4 | Follow competitor channels (their working topics → our original videos) | `src/competitors.py`, `src/genre_topics.py`, `src/daily_runner.py`, `src/channels.py` |
| 5 | Designed thumbnail style "Future Science Editorial" | `src/future_thumbnail.py`, `src/thumbnails.py`, `fonts/` |
| 6 | Per-channel brand kit + channel identity on the dashboard | `src/brand.py`, `data/brand/<channel>/`, `web_dashboard.py` |
| 7 | Style check against your own examples, with auto-correction | `src/style_match.py`, `src/future_thumbnail.py` |
| 8 | Release schedule: fixed times per channel, 4 h apart; workflow uses each channel's Shorts count | `src/schedule.py`, `.github/workflows/daily-videos.yml` |
| 9 | Future-science script rules (no future told as past, no invented studies) | `src/language.py` |
| 10 | Small fixes: dashboard with no channels, click-to-copy everywhere | `web_dashboard.py` |

---

## 1. No video uploads without a verified thumbnail

**What it does**
- Before any upload (Short or long) the thumbnail is checked: file exists and
  opens, at least 1280×720 and 16:9 (a Short may also be 1080×1920, 9:16),
  under 2 MB (re-compressed automatically if bigger), not blank / black.
- A failing thumbnail is remade once; if it still fails the video waits.
- Upload order: video goes up **private** → thumbnail is set → only then is it
  scheduled / made public. If the thumbnail cannot be set, the video stays
  private and the retry sets it and releases it.
- A channel not phone-verified for custom thumbnails does not upload at all
  (it would only pile up private videos).
- Switch: `REQUIRE_THUMBNAIL=true` in `.env` (false = old behaviour).
- Dashboard: each video card shows its thumbnail, "✓ verified 1280×720" or
  "✗ not ready: reason · upload on hold", and a **Remake thumbnail** button.

**Prompt**
```
Add a hard rule to this YouTube bot: no Short or long video may be uploaded
without a verified custom thumbnail.
1. New module thumbnail_check.py: check_thumbnail(path) -> ok/issues/size.
   Checks: file exists and decodes (OpenCV), >=1280x720 and 16:9 (or >=720x1280
   and 9:16 for Shorts), <=2 MB (YouTube limit; re-save as JPEG at lower quality
   if bigger), not blank (grey std-dev < 10) and not almost black. Cache by
   path+mtime. ensure_ready(path, regenerate) remakes the thumbnail once if it
   fails, else raises ThumbnailNotReady. Setting REQUIRE_THUMBNAIL (default true).
2. In the single upload function: check first and raise ThumbnailNotReady before
   any API call. Upload with privacyStatus=private and no publishAt, set the
   thumbnail, then videos.update the status to the intended one (publishAt or
   public). If thumbnails.set fails, raise an error that keeps the video private.
   Add release_video(url, channel, publish_at) that schedules it later or makes it
   public if the booked time has passed.
3. In the render pipeline and the retry queue: run ensure_ready right after the
   thumbnail is made; a ThumbnailNotReady keeps the video pending (no API quota
   used, no upload back-off). When a channel lacks thumbnail permission, do not
   upload; when a retry finally sets the thumbnail, release the private video.
4. Dashboard video cards: show the thumbnail, the check result, and a
   "Remake thumbnail" button (remake, check, then finish a held upload).
Test with a mocked YouTube client: good thumbnail (insert private -> thumbnail
-> update), bad thumbnail (no API call), no permission (no API call),
thumbnail failure (video stays private), release later.
```

## 2. Per-platform upload times + thumbnail on every video

**What it does**
- Each video card in the Video Library shows one line per platform:
  YouTube / Facebook / TikTok — 🟢 uploaded at …, 🟡 goes public / goes live
  at …, or the next automatic try; 🔴 failed with the reason. Platform names
  link to the post.
- Facebook / TikTok posts now store when they go live (`scheduled_for`).
- The library player shows the thumbnail as its poster.
- The public status page (GitHub Pages) shows the same thumbnail and timeline
  for "Last 24 hours" and "Going public next". Thumbnails are kept between runs
  (fetched back from the live page).
- Overview card "Thumbnail check" shows ON/OFF and how many videos are held.

**Prompt**
```
In this bot's dashboard Video Library, show for every video when it went up or
goes up on each platform.
1. Add a column scheduled_for to the social uploads table (migration) and save
   the go-live time when a Facebook post is scheduled or a TikTok post is
   booked.
2. New shared module platform_times.py with platform_timeline(video_row,
   social_rows, social_settings, upload_pause) -> list of
   {name, icon, link, steps:[{state: done|wait|fail, text, when}]}:
   YouTube: Uploaded <upload_date>; Goes public <publish_at> / Public since;
   private until thumbnail is set + next try; not uploaded yet + next automatic
   try (quota back-off time or the next scheduled run); waiting for approval;
   will not upload (reason). Facebook/TikTok: Uploaded, Goes live / Live since,
   Uploading, Failed: reason; "not posted yet · posts with YouTube at" when auto
   posting is on; hide platforms that are not set up.
3. Render it on each card with green/yellow/red dots and local times; use the
   thumbnail as the <video poster> (preload="none").
4. Use the same function on the public status page, with a 320x180 copy of each
   thumbnail in site/thumbs/<id>.jpg (fetch it back from the live site when the
   local file is gone; for public videos fall back to i.ytimg.com mqdefault).
```

## 3. Daily YouTube thumbnail audit

**What it does**
- Every GitHub run looks at each connected channel's uploads of the last 7
  days **on YouTube itself** (Shorts, long, also videos uploaded by hand).
- Spots a missing custom thumbnail without spending quota: YouTube's shown
  picture (`i.ytimg.com/vi/<id>/hqdefault.jpg`) equals one of its own frames
  (`hq1/hq2/hq3.jpg`) when there is no custom thumbnail (difference ≈ 0; a
  custom one differs by 28+).
- Fix: the bot's own card for that video → a fresh one from its script → one
  made from the title. Never touches a custom thumbnail you set yourself.
- Limits: re-set at most every 12 h (YouTube cache), 5 tries, 10 per channel
  per run. Private / scheduled videos are checked once public.
- CLI: `python -m src.cli audit-thumbnails --days 7 [--fix false] [--channel id]`.
- Dashboard (Overview → Thumbnail check): last result, problem videos, **Check
  YouTube now** button.

**Prompt**
```
Add a daily thumbnail audit to this YouTube bot (module thumbnail_audit.py).
For every connected channel: channels.list(mine) -> uploads playlist ->
playlistItems (last 7 days) -> videos.list (status, duration). For each video
download i.ytimg.com/vi/<id>/hqdefault.jpg and hq1/hq2/hq3.jpg, shrink to 48x36
grey, mean absolute difference; min < 8 = "missing" (YouTube shows its own
frame), else "custom"; 404 = "unknown" (not public yet). For a missing one:
use the bot's own thumbnail for that video if it exists and passes the check,
else regenerate it from the saved script, else make one from the title; call
thumbnails.set. Keep a table thumbnail_audit(video_id, channel, title, state,
checked_at, fixed_at, tries, note); do not set again within 12 h, give up after
5 tries, max 10 fixes per channel per run, stop on permission / rate-limit
errors. CLI command audit-thumbnails (--days, --fix, --channel), a step in the
daily GitHub workflow after the uploads (continue-on-error), and a dashboard
card with the counts, problem videos and a "Check YouTube now" button.
Never replace a custom thumbnail. Test with a mocked thumbnails.set.
```

## 4. Follow competitor channels

**What it does**
- Per channel list of competitor YouTube channels (URL or @handle), saved on
  the dashboard (Overview → Competitors).
- Every 12 h the bot reads their last 30 days of videos (3–4 API units per
  channel) and scores each: views per day ÷ that channel's median views per day.
  2× = a topic their audience is hungry for.
- The next Short / long video takes the best unused subject. **Only the subject
  is used**: the writer is told to take its own angle, own words, a clearly
  different title, never name the channel. A title too close to theirs (60 %
  of the words, or 3 words in a row) is written again. Subjects we already
  covered are skipped. Channel rules (niche, facts) still apply.
- Dashboard: competitor cards with their YouTube picture, subscribers, videos
  in 30 days, best ×; click one to filter; Shorts / Long and "next in line /
  ours made" filters; video cards with thumbnail, "× usual" badge, views, age,
  and which of our videos came from it; 8 per page with page buttons.
- CLI: `python -m src.cli competitors --channel <id> [--add "url1,url2"]`.

**Prompt**
```
Add "follow competitors" to this YouTube bot (module competitors.py).
1. Each channel gets a list "competitors" (YouTube URLs or @handles) saved from
   the dashboard. Resolve with channels.list (forHandle / id / forUsername,
   search only as last resort); store id, name, avatar, subscribers.
2. Every 12 h read each competitor's last 30 days of uploads (playlistItems +
   videos.list statistics/contentDetails). Score = views per day / that
   channel's median views per day (ignore videos younger than 12 h). Table
   competitor_videos(channel, video_id, competitor, title, views, published_at,
   short, ratio, used_at, our_title).
3. next_idea(channel, kind): best unused video with ratio >= 1, preferring the
   same kind (Short/long), skipping subjects our own titles already cover;
   reserve it. Add to the script prompt ONLY their title and ratio with rules:
   same general subject, own angle, own words from well-known facts, never quote
   or retell their video, title clearly different (never 3 of their words in a
   row), never mention any channel; channel rules still apply. If our title is
   too similar (>=60% shared words or a shared 3-word run) write it again.
   Record our title against their video. Do the same for the daily long video.
4. Dashboard card: textarea of competitors + Save, "Read them now", channel
   cards with avatar/subscribers/videos in 30 days/best x (click = filter),
   Shorts/Long and next/made filters, video cards with i.ytimg mqdefault
   thumbnail, "x usual" badge, views, age, our video status; 8 per page with
   Prev / 1 2 3 / Next.
```

## 5. Designed thumbnail style "Future Science Editorial"

**What it does**
- `"thumbnail_style": "future"` on a channel gives every thumbnail this look:
  graphite #111318 background with a faint blueprint grid, ivory headline in a
  heavy italic (Archivo Black, slanted), the year / key word in graphite on an
  orange slanted bar with a light-to-deep orange gradient and glow, a capital
  supporting line with orange key words and an orange slash, a scientific label
  panel, "FIG. 01 — CONCEPTUAL RECONSTRUCTION", orange bottom line, the
  channel's logo.
- Long: 1280×720, headline left, photorealistic visual right fading into the
  background. Short: 1080×1920, logo on top, headline in the middle, visual
  below.
- The AI writes the headline (2–5 words, one big word or year; a Short's big
  word at most 6 characters), the supporting line, labels and the visual prompt,
  **from the channel's saved style guide**. The visual comes from Cloudflare
  FLUX or Pollinations.
- Fonts (OFL, Google Fonts) are in `fonts/`.

**Prompt**
```
Add a designed thumbnail style to this bot, drawn with Pillow (module
future_thumbnail.py), used when a channel has "thumbnail_style": "future".
Palette: graphite #111318, ivory #F4F2ED, orange #FF6A00, steel #8E959C, ice
#D9E4E8. 1) An AI call turns the video title (plus the channel's style guide
text) into JSON {top, big, sub (with *orange* words), labels[0-4], visual}.
2) Make a photorealistic visual from "visual" (Cloudflare FLUX, else
Pollinations; 16:9 or 9:16). 3) Long 1280x720: grid on the left, visual on the
right 860 px fading in from the left; logo top-left; "top" in Archivo Black
~150 px, slanted 0.2, ivory with soft shadow; an orange parallelogram bar with a
vertical gradient (255,150,30) -> (240,84,0), glow and a bright top edge, the
"big" word in graphite Archivo Black ~190 px slanted; capital supporting line in
Sora Bold ~31 px, 2 lines, orange slash; label panel on the right; annotation
"FIG. 01 — CONCEPTUAL RECONSTRUCTION"; 4 px orange bottom line. Short 1080x1920:
logo centred on top, "top" ~240 px centred, bar ~940 px wide centred, visual
from y≈500 fading in, dark bottom fade. Keep all sizes in a SPEC dict. Labels
longer than 16 characters are left out, never cut. Accept 9:16 in the thumbnail
check for Shorts. Hook it into create_thumbnail() after the manual-thumbnail
check, falling back to the normal card on any error.
```

## 6. Brand kit per channel + channel identity

**What it does**
- `data/brand/<channel>/`: `style.md` (thumbnail style guide — the headline
  writer reads it), `logo.png` (transparent, drawn on every thumbnail),
  `logo_reference.jpg`, `examples/` (your hand-made thumbnails), `samples/`
  (the bot's latest sample cards + their style check).
- Overview → **Brand & thumbnail style**: style picker, logo (upload PNG),
  colours parsed from the guide, fonts, bot samples with **Make new samples**,
  your examples with upload / delete, editable style guide.
- Channel tabs and the header show the channel's own YouTube picture, banner,
  @handle, subscribers, videos and views (read with 1 API unit, cached 12 h).

**Prompt**
```
Give every channel of this bot a brand kit in data/brand/<channel id>/:
style.md (the thumbnail style guide; pass its text to the thumbnail headline
prompt), logo.png (transparent, drawn on thumbnails instead of a drawn mark),
logo_reference image, examples/ (hand-made thumbnails), samples/ (the bot's
latest long + Short sample). Module brand.py with style_text/save_style,
palette() (hex codes parsed from the guide), examples/samples/logo helpers,
save_upload(kind=example|logo|logo_reference), make_samples(channel), and
youtube_identity(channel): channels.list(mine, snippet+statistics+
brandingSettings) cached 12 h in youtube.json (gitignored) -> avatar, banner,
handle, subscribers, videos, views. Dashboard: channel tabs with the avatar and
subscriber count; an active-channel header with avatar, banner, handle, stats,
palette swatches; an Overview card "Brand & thumbnail style" with a style
dropdown (writes thumbnail_style to channels.json), logo upload (PNG only),
colours, fonts, samples gallery + "Make new samples", examples gallery with
upload/delete, and an editable style guide.
```

## 7. Style check against your own examples (check and balance)

**What it does**
- After a designed thumbnail is drawn, `style_match.py` measures it and every
  example of the same shape: orange bar height and width (by hue, gaps closed),
  how much of the headline area is ivory text (size × weight), and whether the
  bar or headline is cut by the card's edge (a long card's bar may bleed off
  the left, like the examples).
- More than 25 % off on any measure fails, with the reason in words
  ("headline size/weight is 32% smaller than your examples"). Cut-off = score
  at most 30, never chosen.
- The composer corrects the sizes and redraws up to twice, keeps the best card
  and saves the result next to it (`<card>.style.json`).

**Prompt**
```
Add a style check that compares each generated thumbnail with the channel's
hand-made examples (data/brand/<channel>/examples), module style_match.py.
measure(path): resize to 320x180 (or 180x320 tall); orange mask by HSV (hue
4-24, sat>150, val>170) closed with a 9x9 kernel; biggest component in the
headline zone -> bar height/width as shares of the card, and whether it touches
the right edge (or either edge on tall cards); ivory mask (R,G>205, B>195,
|R-B|<40) mean over the headline zone -> headline weight; headline letters
touching the side edges. reference(): average of the examples of the same
shape. compare(): ratios card/reference; fail when any is off by >25%, issues in
plain words, score = 100*(1-worst), at most 30 when something is cut by an edge.
In the composer: draw, compare, adjust the SPEC (headline size by
sqrt(1/ratio), bar padding/size by 1/ratio, shrink widths when cut), redraw up
to twice, keep the best, save the check as JSON beside the card.
```

## 8. Release schedule and Shorts count

**What it does**
- Release times per channel genre in `src/schedule.py` (US Eastern). For
  Chronovanta: Shorts 09:00, 13:00, 21:00 and the long documentary 17:00 —
  every release 4 h from the next. 3 Shorts a day, long video Mon / Wed / Fri.
- The daily workflow no longer forces 2 Shorts: blank = each channel's own
  `topics_per_day`.

**Prompt**
```
In this bot's schedule module give each channel fixed daily release times in
US Eastern, separate for Shorts and long videos, at least 4 hours apart
(e.g. Shorts 09:00, 13:00, 21:00 and long 17:00); a video takes the first free
time at least 45 min ahead, today or a later day. In the daily GitHub workflow
make the Shorts-per-channel input default to blank so each channel's own
topics_per_day is used. Verify by reserving two days of slots and printing the
gaps.
```

## 9. Future-science script rules

**What it does** — for any channel whose genre contains "future": only
technology / AI / robotics / biotech / energy / space / future-city topics;
anything after today is "could / might", never past tense; three layers per
video (exists today → being tested → possible later); no invented studies,
quotes, numbers or scientists; titles as questions or scenarios.

**Prompt**
```
Add genre rules to this bot's script prompt for channels whose genre contains
"future": topics only technology, AI, robotics, biotechnology, energy, space or
future cities; today's month and year are given and anything later is a
possibility ("could", "might"), never past tense, never "was discovered";
each video in three layers: what exists today, what researchers test now (with
limits), what might come later (labelled a scenario); only real, well-known
technologies and organisations, never an invented study, quote, percentage or
scientist; the title is a question or a scenario, never a certain claim.
```

## 10. Small fixes

- Dashboard no longer crashes with an empty channel list: it opens the New
  channel page.
- Click-to-copy works on every grey value of the page (the Facebook guide
  too): one document-level click handler, the real value kept so a double click
  never copies "✅ copied", `execCommand` fallback.
