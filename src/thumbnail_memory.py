"""The bot remembers the thumbnail it made for every uploaded video, then checks
that YouTube really shows that picture, and puts it back when it does not.

Why: setting a thumbnail can fail quietly (YouTube keeps its own frame, or a
retry put another video's card on), and the files of a GitHub run are gone the
moment it ends. So at upload time a copy of the card is stored in the bot's
database, which travels with the bot-state branch, together with the channel it
was made for.

The check compares the picture YouTube serves for the video with the stored
copy, in the card's own shape: a long video's card (16:9) against mqdefault.jpg,
a Short's card (9:16) against sardefault.jpg, the picture the Shorts lists show.
The card is stored exactly as made. (The first version squeezed every card to
1280x720 and compared Shorts with the 16:9 picture, so it never matched and kept
putting a squashed card on Shorts. Those copies sit in the old table
thumbnail_memory and are never read again.)

    same card            mean grey difference ~1
    a different picture  20 or more (measured on the real channels)

A private or scheduled video has no public picture yet; it is checked once it
is public, by the end-of-run thumbnail audit.

Before anything is set the video's channel is confirmed: the stored card must
have been made for this channel, still look like this channel's style, and the
video must really be on the channel this login belongs to.

    python -m src.cli verify-thumbnails
"""
from __future__ import annotations

import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import settings

MATCH_LIMIT = 8.0            # mean grey difference at or below this = our card
LANDSCAPE_SIZE = (64, 36)
PORTRAIT_SIZE = (36, 64)
TABLE = "thumbnail_cards"
VERIFY_DELAY_SECONDS = 45    # YouTube needs a moment to show a freshly set thumbnail
REFIX_AFTER = timedelta(minutes=30)
MAX_FIXES = 4                # per video, so a stubborn video cannot eat the thumbnail allowance
KEEP_DAYS = 45

_LOCK = threading.Lock()
_PENDING: list[threading.Thread] = []
_CHANNEL_IDS: dict[str, str] = {}


# ------------------------------------------------------------------ storage

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
               video_id TEXT PRIMARY KEY,
               channel TEXT NOT NULL,
               youtube_channel_id TEXT,
               image BLOB NOT NULL,
               fingerprint BLOB NOT NULL,
               saved_at TEXT NOT NULL,
               state TEXT NOT NULL DEFAULT 'saved',
               checked_at TEXT,
               fixed_at TEXT,
               fixes INTEGER NOT NULL DEFAULT 0,
               note TEXT)"""
    )
    return conn


def _portrait(image) -> bool:
    return image.shape[0] > image.shape[1]


def _fingerprint(gray, portrait: bool) -> "object":
    import cv2

    return cv2.resize(gray, PORTRAIT_SIZE if portrait else LANDSCAPE_SIZE, interpolation=cv2.INTER_AREA)


def _video_id(video_url_or_id: str) -> str:
    text = str(video_url_or_id or "")
    return text.split("v=", 1)[1].split("&", 1)[0] if "v=" in text else text


def remember(video_url_or_id: str, channel, thumbnail_path: Path) -> bool:
    """Store the card made for this video. False when there is nothing to store."""
    import cv2

    path = Path(thumbnail_path or "")
    image = cv2.imread(str(path)) if path.is_file() else None
    if image is None:
        print(f"[thumbnail-memory] nothing to remember for {video_url_or_id}: {path}")
        return False
    # Stored in its own shape: a Short's card is 9:16 and must stay 9:16.
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return False
    fingerprint = _fingerprint(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), _portrait(image))
    video_id = _video_id(video_url_or_id)
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f"""INSERT INTO {TABLE} (video_id, channel, image, fingerprint, saved_at, state)
                   VALUES (?, ?, ?, ?, ?, 'saved')
                   ON CONFLICT(video_id) DO UPDATE SET
                       channel=excluded.channel, image=excluded.image,
                       fingerprint=excluded.fingerprint, saved_at=excluded.saved_at,
                       state='saved', note=NULL""",
                (video_id, str(getattr(channel, "id", "") or "default"), encoded.tobytes(),
                 fingerprint.tobytes(), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    return True


def _row(video_id: str):
    conn = _conn()
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(f"SELECT * FROM {TABLE} WHERE video_id = ?", (video_id,)).fetchone()
    finally:
        conn.close()


def _update(video_id: str, state: str, note: str = "", fixed: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(
                f"""UPDATE {TABLE} SET state = ?, note = ?, checked_at = ?,
                          fixed_at = CASE WHEN ? THEN ? ELSE fixed_at END,
                          fixes = fixes + CASE WHEN ? THEN 1 ELSE 0 END
                   WHERE video_id = ?""",
                (state, note[:300], now, fixed, now, fixed, video_id),
            )
            conn.commit()
        finally:
            conn.close()


def saved_card(video_id: str) -> Path | None:
    """The stored card written back to a file, for set_thumbnail."""
    row = _row(video_id)
    if row is None:
        return None
    out = settings.root / "runs" / "thumbnail_memory" / f"{video_id}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(row["image"]))
    return out


def card_for(video_id: str, channel) -> Path | None:
    """The stored card, but only when it was made for this channel."""
    row = _row(_video_id(video_id))
    if row is None or str(row["channel"]) != str(getattr(channel, "id", "")):
        return None
    return saved_card(row["video_id"])


def has_memory(video_id: str) -> bool:
    return _row(_video_id(video_id)) is not None


def prune(days: int = KEEP_DAYS) -> int:
    """Forget cards of videos older than `days`; they are long settled."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _LOCK:
        conn = _conn()
        try:
            removed = conn.execute(f"DELETE FROM {TABLE} WHERE saved_at < ?", (since,)).rowcount
            conn.commit()
        finally:
            conn.close()
    return int(removed or 0)


# ------------------------------------------------------------------ checking

def _stored_image(row):
    import cv2
    import numpy as np

    return cv2.imdecode(np.frombuffer(bytes(row["image"]), np.uint8), cv2.IMREAD_GRAYSCALE)


def _shown_fingerprint(video_id: str, portrait: bool):
    """YouTube's current thumbnail in the card's shape, or None while it is not public."""
    import cv2
    import numpy as np

    name = "sardefault" if portrait else "mqdefault"
    request = urllib.request.Request(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg",
                                     headers={"User-Agent": "Mozilla/5.0 story-bot-studio"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    gray = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None or _portrait(gray) != portrait:
        return None
    return _fingerprint(gray, portrait)


def compare(video_url_or_id: str) -> tuple[str, float | None]:
    """('ours' | 'different' | 'not_public' | 'no_memory', difference)."""
    import numpy as np

    video_id = _video_id(video_url_or_id)
    row = _row(video_id)
    if row is None:
        return "no_memory", None
    stored = _stored_image(row)
    if stored is None:
        return "no_memory", None
    portrait = _portrait(stored)
    shown = _shown_fingerprint(video_id, portrait)
    if shown is None:
        return "not_public", None
    mine = _fingerprint(stored, portrait)
    difference = float(np.abs(mine.astype(float) - shown.astype(float)).mean())
    return ("ours" if difference <= MATCH_LIMIT else "different"), difference


def _own_channel_id(channel) -> str:
    key = str(getattr(channel, "token_path", "") or "default")
    if key not in _CHANNEL_IDS:
        from .youtube_upload import _youtube

        youtube = _youtube(channel.client_secret_path, channel.token_path)
        items = youtube.channels().list(part="id", mine=True).execute().get("items") or []
        _CHANNEL_IDS[key] = items[0]["id"] if items else ""
    return _CHANNEL_IDS[key]


def _is_short(youtube, video_id: str) -> bool:
    """A Short is vertical; YouTube reports no shape, so its duration (<= 3 min) decides."""
    from .thumbnail_audit import _duration_seconds

    items = youtube.videos().list(part="contentDetails", id=video_id).execute().get("items") or []
    duration = items[0]["contentDetails"].get("duration", "") if items else ""
    return 0 < _duration_seconds(duration) <= 180


def channel_problem(video_id: str, channel) -> str:
    """Why the stored card must not be set on this video ('' = the channel is right)."""
    row = _row(video_id)
    if row is None:
        return "no stored card"
    if str(row["channel"]) != str(channel.id):
        return f"the stored card was made for '{row['channel']}', not '{channel.id}'"
    from .youtube_upload import _youtube

    youtube = _youtube(channel.client_secret_path, channel.token_path)
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items") or []
    if not items:
        return "this login cannot see the video (deleted, or on another channel)"
    on_channel = items[0]["snippet"].get("channelId", "")
    stored = _stored_image(row)
    if stored is None or _portrait(stored) != _is_short(youtube, video_id):
        return "the stored card's shape (portrait/landscape) does not fit this video"
    own = _own_channel_id(channel)
    if own and on_channel != own:
        return f"the video is on channel {on_channel}, but this login is channel {own}"
    with _LOCK:
        conn = _conn()
        try:
            conn.execute(f"UPDATE {TABLE} SET youtube_channel_id = ? WHERE video_id = ?",
                         (on_channel, video_id))
            conn.commit()
        finally:
            conn.close()
    from .style_match import style_ok

    card = saved_card(video_id)
    styled, problem = style_ok(card, channel) if card else (False, "card missing")
    if not styled:
        return f"the stored card does not look like {channel.id}'s style: {problem}"
    return ""


def verify(video_url_or_id: str, channel, fix: bool = True) -> str:
    """Check one video; put the stored card back when YouTube shows something else."""
    video_id = _video_id(video_url_or_id)
    state, difference = compare(video_id)
    tag = f"[thumbnail-memory] {getattr(channel, 'id', '?')} {video_id}"
    if state == "no_memory":
        return f"{tag}: no stored card, nothing to compare"
    if state == "not_public":
        _update(video_id, "waiting", "not public yet; checked again once it is")
        return f"{tag}: not public yet, checked again once it is"
    if state == "ours":
        _update(video_id, "ours", f"difference {difference:.1f}")
        return f"{tag}: our thumbnail is on (difference {difference:.1f})"

    row = _row(video_id)
    note = f"YouTube shows another picture (difference {difference:.1f})"
    if not fix:
        _update(video_id, "different", note)
        return f"{tag}: {note}"
    if row["fixed_at"] and datetime.now(timezone.utc) - datetime.fromisoformat(row["fixed_at"]) < REFIX_AFTER:
        _update(video_id, "fix_waiting", note + "; set recently, waiting for YouTube to show it")
        return f"{tag}: {note}; set recently, waiting for YouTube to show it"
    if int(row["fixes"]) >= MAX_FIXES:
        _update(video_id, "different", note + f"; gave up after {row['fixes']} tries")
        return f"{tag}: {note}; gave up after {row['fixes']} tries"
    from .pending_uploads import thumbnail_upload_allowed

    if not thumbnail_upload_allowed(channel.id):
        _update(video_id, "different", note + "; channel not verified for custom thumbnails")
        return f"{tag}: {note}; channel not verified for custom thumbnails (youtube.com/verify)"
    try:
        problem = channel_problem(video_id, channel)
    except Exception as exc:
        problem = f"could not confirm the channel: {exc}"
    if problem:
        _update(video_id, "wrong_channel", problem)
        return f"{tag}: NOT fixed, {problem}"
    from .youtube_upload import set_thumbnail

    try:
        set_thumbnail(video_id, saved_card(video_id), attempts=2,
                      client_secret_file=channel.client_secret_path, token_file=channel.token_path)
    except Exception as exc:
        _update(video_id, "fix_failed", f"{note}; setting it failed: {exc}")
        return f"{tag}: {note}; setting it FAILED: {str(exc)[:160]}"
    _update(video_id, "fixed", note + "; stored card set again", fixed=True)
    return f"{tag}: {note}; stored card set again"


def verify_later(video_url: str, channel, delay: float = VERIFY_DELAY_SECONDS) -> None:
    """Check a just-uploaded public video after a short wait, without holding up the run."""
    def work() -> None:
        time.sleep(delay)
        try:
            print(verify(video_url, channel))
        except Exception as exc:
            print(f"[thumbnail-memory] check of {video_url} failed: {exc}")

    # Not a daemon: the process waits for the check before it exits.
    thread = threading.Thread(target=work, name=f"thumb-check-{_video_id(video_url)}")
    thread.start()
    _PENDING.append(thread)


def verify_recent(days: int = 7, fix: bool = True, channel_id: str | None = None) -> list[str]:
    """Check every remembered video of the last `days` that is not settled yet."""
    from .channels import load_channels
    from .youtube_accounts import channel_for_account, connected_accounts

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _conn()
    try:
        rows = conn.execute(
            f"""SELECT video_id, channel FROM {TABLE}
               WHERE saved_at >= ? AND state != 'ours' ORDER BY saved_at""",
            (since,),
        ).fetchall()
    finally:
        conn.close()
    channels = {}
    for base in load_channels():
        for account in connected_accounts(base.id):
            channels.setdefault(base.id, []).append(channel_for_account(base.id, account.id))
    messages: list[str] = []
    for video_id, stored_channel in rows:
        if channel_id and stored_channel != channel_id:
            continue
        candidates = channels.get(stored_channel) or []
        if not candidates:
            messages.append(f"[thumbnail-memory] {stored_channel} {video_id}: channel is not connected here")
            continue
        # With several logins on one channel, the one the video is on is found by channel_problem.
        message = ""
        for channel in candidates:
            message = verify(video_id, channel, fix=fix)
            if "NOT fixed" not in message:
                break
        messages.append(message)
    removed = prune()
    if removed:
        messages.append(f"[thumbnail-memory] forgot {removed} card(s) older than {KEEP_DAYS} days")
    return messages
