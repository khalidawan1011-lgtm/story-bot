"""Bot-to-bot API: other bots manage this one, and this one calls other bots.

Two halves, both managed from the dashboard's "Bot API" tab:

1. This bot's own API (server). The dashboard creates API keys; another bot
   sends one as `Authorization: Bearer sbk_...` to /api/v1/... Each key has
   scopes: "read" (status, channels, accounts, videos, topics) and "write"
   (add topics, start videos, change a video's SEO), and the channels it may
   touch: ticked channels only, or "*" for all channels including new ones.
   Requests are checked against a SHA-256 hash of the key. The key itself is
   also kept in data/api_keys.json (never in git) so the dashboard can copy it
   again later, on request only; it is never put in the page or the cookie.

2. Connected bots (client). Another bot's base URL and key are saved in
   data/connected_bots.json; `call(name, method, path, body)` talks to it, and
   the dashboard can test the link.

Any bot that answers GET /api/v1 with {"bot": ..., "api": 1, ...} and accepts a
Bearer key can be connected; docs/BOT_API.md describes the contract so the SEO
bot can offer the same endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, g, jsonify, request

from .config import settings

API_VERSION = 1
BOT_NAME = "story-bot"
SCOPES = ("read", "write")
KEY_PREFIX = "sbk_"

_KEYS_PATH = settings.root / "data" / "api_keys.json"
_BOTS_PATH = settings.root / "data" / "connected_bots.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ own keys

ALL_CHANNELS = "*"


def _clean_channels(channels) -> list[str]:
    channels = [str(c).strip() for c in (channels or []) if str(c).strip()]
    return [ALL_CHANNELS] if ALL_CHANNELS in channels else sorted(set(channels))


def channel_allowed(row: dict, channel_id: str) -> bool:
    channels = row.get("channels", [ALL_CHANNELS])  # keys made before channel ticks: all
    return ALL_CHANNELS in channels or channel_id in channels


def create_key(name: str, scopes: list[str], channels: list[str] | None = None) -> str:
    """A new key; returned once and never stored in plain text."""
    scopes = [s for s in scopes if s in SCOPES] or ["read"]
    channels = _clean_channels(channels)
    if not channels:
        raise ValueError("Tick at least one channel (or All channels) for this key.")
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    with _LOCK:
        rows = _read(_KEYS_PATH)
        rows.append({
            "id": secrets.token_hex(4), "name": (name or "unnamed").strip()[:60],
            "scopes": scopes, "channels": channels, "hash": _hash(key), "key": key, "hint": key[:8] + "…" + key[-4:],
            "created_at": _now(), "last_used_at": None, "revoked": False,
        })
        _write(_KEYS_PATH, rows)
    return key


def list_keys() -> list[dict]:
    return [{**{k: v for k, v in row.items() if k not in ("hash", "key")}, "copyable": bool(row.get("key"))}
            for row in _read(_KEYS_PATH)]


def key_text(key_id: str) -> str | None:
    """The full key, for the dashboard's Copy button. Not for revoked keys."""
    for row in _read(_KEYS_PATH):
        if row.get("id") == key_id and not row.get("revoked"):
            return row.get("key")
    return None


def delete_key(key_id: str) -> bool:
    """Remove a key from the list entirely; a bot using it is cut off at once."""
    with _LOCK:
        rows = _read(_KEYS_PATH)
        kept = [r for r in rows if r.get("id") != key_id]
        _write(_KEYS_PATH, kept)
    return len(kept) != len(rows)


def set_key_channels(key_id: str, channels: list[str]) -> bool:
    """Change which channels an existing key may use; takes effect at once."""
    channels = _clean_channels(channels)
    if not channels:
        raise ValueError("Tick at least one channel (or All channels), or revoke the key.")
    with _LOCK:
        rows = _read(_KEYS_PATH)
        found = False
        for row in rows:
            if row.get("id") == key_id and not row.get("revoked"):
                row["channels"] = channels
                found = True
        _write(_KEYS_PATH, rows)
    return found


def revoke_key(key_id: str) -> bool:
    with _LOCK:
        rows = _read(_KEYS_PATH)
        found = False
        for row in rows:
            if row.get("id") == key_id and not row.get("revoked"):
                row["revoked"] = True
                row["revoked_at"] = _now()
                row.pop("key", None)  # a revoked key is never copied again
                found = True
        _write(_KEYS_PATH, rows)
    return found


def _check_key(key: str) -> dict | None:
    if not key.startswith(KEY_PREFIX):
        return None
    digest = _hash(key)
    with _LOCK:
        rows = _read(_KEYS_PATH)
        for row in rows:
            if not row.get("revoked") and hmac.compare_digest(row.get("hash", ""), digest):
                row["last_used_at"] = _now()
                _write(_KEYS_PATH, rows)
                return row
    return None


# ------------------------------------------------------------------ connected bots

def list_bots(include_key: bool = False) -> list[dict]:
    rows = _read(_BOTS_PATH)
    if include_key:
        return rows
    return [{**{k: v for k, v in row.items() if k != "api_key"},
             "key_hint": (row.get("api_key") or "")[:6] + "…"} for row in rows]


def _clean_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("The URL must start with http:// or https://, e.g. http://127.0.0.1:8100")
    return url


def add_bot(name: str, base_url: str, api_key: str) -> dict:
    name = (name or "").strip()[:40]
    if not name:
        raise ValueError("Give the bot a name.")
    if not (api_key or "").strip():
        raise ValueError("Paste the other bot's API key.")
    row = {"name": name, "base_url": _clean_url(base_url), "api_key": api_key.strip(),
           "added_at": _now(), "last_checked_at": None, "last_ok": None, "last_result": ""}
    with _LOCK:
        rows = [r for r in _read(_BOTS_PATH) if r.get("name") != name]
        rows.append(row)
        _write(_BOTS_PATH, rows)
    return row


def remove_bot(name: str) -> bool:
    with _LOCK:
        rows = _read(_BOTS_PATH)
        kept = [r for r in rows if r.get("name") != name]
        _write(_BOTS_PATH, kept)
    return len(kept) != len(rows)


def call(name: str, method: str, path: str, body: dict | None = None, timeout: int = 30):
    """Call a connected bot: call("seo-bot", "GET", "/api/v1/status")."""
    bot = next((r for r in _read(_BOTS_PATH) if r.get("name") == name), None)
    if bot is None:
        raise KeyError(f"No connected bot named '{name}'.")
    url = bot["base_url"] + ("/" + path.lstrip("/"))
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper(), headers={
        "Authorization": f"Bearer {bot['api_key']}", "Accept": "application/json",
        "Content-Type": "application/json", "User-Agent": f"{BOT_NAME}/{API_VERSION}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{name} answered HTTP {exc.code}: {detail}") from exc
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return raw.decode("utf-8", "replace")


def test_bot(name: str) -> tuple[bool, str]:
    """Ask the bot who it is, then whether the key works; the result is saved."""
    ok, result = False, ""
    try:
        about = call(name, "GET", "/api/v1")
        status = call(name, "GET", "/api/v1/status")
        who = about.get("bot", "?") if isinstance(about, dict) else "?"
        ok, result = True, f"connected to '{who}'; key accepted ({json.dumps(status)[:160]})"
    except Exception as exc:
        result = str(exc)[:300]
    with _LOCK:
        rows = _read(_BOTS_PATH)
        for row in rows:
            if row.get("name") == name:
                row.update(last_checked_at=_now(), last_ok=ok, last_result=result)
        _write(_BOTS_PATH, rows)
    return ok, result


# ------------------------------------------------------------------ HTTP API

def require(scope: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            key = header[7:].strip() if header.lower().startswith("bearer ") else ""
            row = _check_key(key) if key else None
            if row is None:
                return jsonify(error="missing or invalid API key",
                               hint="send Authorization: Bearer sbk_..."), 401
            if scope not in row.get("scopes", []):
                return jsonify(error=f"this key has no '{scope}' permission"), 403
            g.api_key = row
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def _channel_or_404(channel_id: str):
    """The channel, or None. A channel this key was not given counts as unknown,
    so a bot cannot even learn which other channels exist."""
    from .channels import load_channels

    if not channel_allowed(g.api_key, channel_id):
        return None
    for channel in load_channels():
        if channel.id == channel_id:
            return channel
    return None


def _channel_summary(channel) -> dict:
    from . import social_accounts, youtube_accounts
    from .pending_uploads import upload_limit_for_channel, uploads_today_count

    social = social_accounts.public_status(channel.id) or {}
    return {
        "id": channel.id, "name": channel.name, "genre": getattr(channel, "genre", ""),
        "language": getattr(channel, "language", ""),
        "uploads_today": uploads_today_count(channel.id),
        "upload_limit": upload_limit_for_channel(channel.id),
        "accounts": [{
            "id": a.id, "name": a.label, "connected": a.connected,
            "uploads_today": uploads_today_count(channel.id, a.id),
            "upload_limit": upload_limit_for_channel(channel.id, a.id),
        } for a in youtube_accounts.list_accounts(channel.id)],
        "facebook": {"connected": bool((social.get("facebook") or {}).get("configured")),
                     "page": (social.get("facebook") or {}).get("verified_name", ""),
                     "auto_upload": bool((social.get("facebook") or {}).get("auto_upload"))},
        "tiktok": {"connected": bool((social.get("tiktok") or {}).get("configured")),
                   "mode": (social.get("tiktok") or {}).get("mode", "")},
    }


def blueprint(start_job, jobs: dict) -> Blueprint:
    """The /api/v1 routes. start_job and jobs come from the dashboard's job runner."""
    bp = Blueprint("bot_api", __name__, url_prefix="/api/v1")

    @bp.get("")
    @bp.get("/")
    def about():
        return jsonify(bot=BOT_NAME, api=API_VERSION, auth="Authorization: Bearer <key>", endpoints=[
            "GET  /api/v1/status                                   read",
            "GET  /api/v1/channels                                 read",
            "GET  /api/v1/channels/<id>                            read",
            "GET  /api/v1/channels/<id>/videos?limit=&type=        read",
            "GET  /api/v1/channels/<id>/topics                     read",
            "POST /api/v1/channels/<id>/topics  {topics, make_video, upload}   write",
            "POST /api/v1/channels/<id>/generate {shorts, upload}             write",
            "POST /api/v1/channels/<id>/videos/<youtube_id>/seo {title, description, tags}  write",
            "GET  /api/v1/jobs/<job_id>                            read",
        ])

    @bp.get("/status")
    @require("read")
    def status():
        from .channels import load_channels

        channels = [c for c in load_channels() if channel_allowed(g.api_key, c.id)]
        running = sum(1 for j in jobs.values() if j.get("status") in ("queued", "running"))
        return jsonify(bot=BOT_NAME, api=API_VERSION, time=_now(), channels=len(channels),
                       jobs_running=running, key=g.api_key.get("name"))

    @bp.get("/channels")
    @require("read")
    def channels():
        from .channels import load_channels

        return jsonify(channels=[_channel_summary(c) for c in load_channels()
                                 if channel_allowed(g.api_key, c.id)])

    @bp.get("/channels/<channel_id>")
    @require("read")
    def channel(channel_id):
        ch = _channel_or_404(channel_id)
        if ch is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        data = _channel_summary(ch)
        try:
            from . import youtube_analytics

            data["analytics"] = youtube_analytics.snapshot(ch)
        except Exception as exc:
            data["analytics"] = {"error": str(exc)[:200]}
        return jsonify(data)

    @bp.get("/channels/<channel_id>/videos")
    @require("read")
    def videos(channel_id):
        import sqlite3

        if _channel_or_404(channel_id) is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        limit = max(1, min(200, int(request.args.get("limit", 50))))
        kind = request.args.get("type", "")
        sql = ("SELECT id, topic, title, COALESCE(content_type,'short') AS content_type, status, video_url, "
               "publish_at, created_at FROM videos WHERE channel = ? AND hidden_at IS NULL")
        params: list = [channel_id]
        if kind in ("short", "long"):
            sql += " AND COALESCE(content_type,'short') = ?"
            params.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        if not settings.db_path.exists():
            return jsonify(videos=[])
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()
        for row in rows:
            url = row.get("video_url") or ""
            row["youtube_id"] = url.split("v=", 1)[1][:11] if "v=" in url else None
        return jsonify(videos=rows)

    @bp.get("/channels/<channel_id>/topics")
    @require("read")
    def topics(channel_id):
        from .lessons import load_topics_for

        ch = _channel_or_404(channel_id)
        if ch is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        items = load_topics_for(ch)
        return jsonify(topics=[{"key": k, "title": v.get("title", k)} for k, v in items.items()])

    @bp.post("/channels/<channel_id>/topics")
    @require("write")
    def add_topics(channel_id):
        ch = _channel_or_404(channel_id)
        if ch is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        body = request.get_json(silent=True) or {}
        prompts = [str(t).strip()[:300] for t in (body.get("topics") or []) if str(t).strip()][:10]
        if not prompts:
            return jsonify(error="send {\"topics\": [\"topic or keyword idea\", ...]} (max 10)"), 400
        make_video = bool(body.get("make_video", False))
        upload = bool(body.get("upload", True))

        def job():
            from .genre_topics import generate_from_prompt
            from .lessons import load_lesson_for
            from .pipeline import run_pipeline

            done = []
            for prompt in prompts:
                key = generate_from_prompt(ch, prompt)
                if make_video:
                    run_pipeline(load_lesson_for(ch, key), upload=upload, channel=ch)
                done.append(key)
            return "topics added: " + ", ".join(done)

        job_id = start_job(f"[{ch.id}] API: {len(prompts)} topic(s) from {g.api_key.get('name')}", job)
        return jsonify(accepted=len(prompts), job_id=job_id, make_video=make_video), 202

    @bp.post("/channels/<channel_id>/generate")
    @require("write")
    def generate(channel_id):
        from .daily_runner import run_daily_batch

        ch = _channel_or_404(channel_id)
        if ch is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        body = request.get_json(silent=True) or {}
        count = max(1, min(4, int(body.get("shorts", 1))))
        upload = bool(body.get("upload", True))

        def job():
            results = run_daily_batch(count=count, upload=upload, channel=ch)
            return "; ".join(f"{t}:{s}" for t, s in results)

        job_id = start_job(f"[{ch.id}] API: {count} Short(s) from {g.api_key.get('name')}", job)
        return jsonify(job_id=job_id, shorts=count, upload=upload), 202

    @bp.post("/channels/<channel_id>/videos/<youtube_id>/seo")
    @require("write")
    def seo(channel_id, youtube_id):
        ch = _channel_or_404(channel_id)
        if ch is None:
            return jsonify(error="unknown channel, or this key is not allowed to use it"), 404
        body = request.get_json(silent=True) or {}
        try:
            changed = update_video_seo(ch, youtube_id, title=body.get("title"),
                                       description=body.get("description"), tags=body.get("tags"))
        except PermissionError as exc:
            return jsonify(error=str(exc)), 403
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception as exc:
            return jsonify(error=str(exc)[:300]), 502
        return jsonify(updated=changed, youtube_id=youtube_id)

    @bp.get("/jobs/<job_id>")
    @require("read")
    def job_status(job_id):
        job = jobs.get(job_id)
        label = str((job or {}).get("label", ""))
        job_channel = label[1:label.index("]")] if label.startswith("[") and "]" in label else ""
        if job is None or (job_channel and not channel_allowed(g.api_key, job_channel)):
            return jsonify(error="unknown job"), 404
        return jsonify(id=job_id, **{k: job.get(k) for k in ("label", "status", "detail", "created_at")})

    return bp


def update_video_seo(channel, youtube_id: str, title=None, description=None, tags=None) -> list[str]:
    """Change a video's title / description / tags on YouTube, keeping everything else."""
    from .youtube_upload import _youtube, can_manage, youtube_description

    if not can_manage(channel.token_path):
        raise PermissionError("this channel's YouTube login cannot edit videos; reconnect it on the dashboard")
    youtube = _youtube(channel.client_secret_path, channel.token_path)
    items = youtube.videos().list(part="snippet", id=youtube_id).execute().get("items") or []
    if not items:
        raise ValueError("this channel's login cannot see that video")
    mine = youtube.channels().list(part="id", mine=True).execute().get("items") or []
    snippet = items[0]["snippet"]
    if mine and snippet.get("channelId") != mine[0]["id"]:
        raise PermissionError("that video is on another YouTube channel")
    changed = []
    if title is not None:
        title = str(title).strip()
        if not 1 <= len(title) <= 100 or "<" in title or ">" in title:
            raise ValueError("title must be 1-100 characters, without < or >")
        snippet["title"] = title
        changed.append("title")
    if description is not None:
        snippet["description"] = youtube_description(str(description))
        changed.append("description")
    if tags is not None:
        if not isinstance(tags, list):
            raise ValueError("tags must be a list of strings")
        clean = [str(t).strip() for t in tags if str(t).strip()]
        if sum(len(t) + 1 for t in clean) > 500:
            raise ValueError("tags are longer than YouTube's 500-character limit")
        snippet["tags"] = clean
        changed.append("tags")
    if not changed:
        raise ValueError("send at least one of title, description, tags")
    keep = {k: snippet[k] for k in ("title", "description", "tags", "categoryId",
                                    "defaultLanguage", "defaultAudioLanguage") if k in snippet}
    youtube.videos().update(part="snippet", body={"id": youtube_id, "snippet": keep}).execute()
    return changed
