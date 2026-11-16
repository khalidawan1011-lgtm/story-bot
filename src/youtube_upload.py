from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import settings


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",  # read the connected channel's name to verify it
]
# Asked for when a channel is (re)connected: also lets the bot change a video's
# privacy (release a video held private until its thumbnail is set).
MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
CONNECT_SCOPES = [*SCOPES, MANAGE_SCOPE]


# YouTube refuses a description over 5000 bytes or with < or > in it
# ("invalidDescription"). A long video's script summary plus its clip credits
# and source line ran past the limit, and the video waited forever.
_DESCRIPTION_BYTES = 4900


def youtube_description(text: str) -> str:
    text = text.replace("<", "(").replace(">", ")")
    if len(text.encode("utf-8")) <= _DESCRIPTION_BYTES:
        return text
    # Drop whole lines from the middle (the script summary), keeping the
    # opening and the closing lines, which carry the hashtags, credits and source.
    lines = text.split("\n")
    head, tail = lines[:4], lines[4:]
    while tail and len("\n".join(head + ["..."] + tail).encode("utf-8")) > _DESCRIPTION_BYTES:
        tail.pop(0)
    trimmed = "\n".join(head + ["..."] + tail)
    return trimmed.encode("utf-8")[:_DESCRIPTION_BYTES].decode("utf-8", "ignore")


class ThumbnailUploadError(RuntimeError):
    def __init__(self, video_url: str, message: str) -> None:
        super().__init__(message)
        self.video_url = video_url


def _credentials(client_secret_file: Path | None = None, token_file: Path | None = None) -> Credentials:
    client_secret_file = client_secret_file or settings.youtube_client_secret_file
    token_file = token_file or settings.youtube_token_file
    creds = None
    if token_file.exists():
        # The scopes this login was granted (an older login has no MANAGE_SCOPE;
        # asking a refresh for more than was granted would fail).
        creds = Credentials.from_authorized_user_file(str(token_file))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not client_secret_file.exists():
            raise FileNotFoundError(f"Missing YouTube client secret: {client_secret_file}")
        # Opening a browser is only ever right on a real desktop. On a server or
        # a CI runner there is nobody to click, so the flow would block until
        # the job is killed; say what is wrong instead.
        if os.getenv("NO_INTERACTIVE_AUTH", "").strip().lower() in {"1", "true", "yes"}:
            raise RuntimeError(
                f"No usable YouTube login in {token_file.name} and this machine "
                "cannot open a browser. Connect the channel on your PC first, "
                "then re-run scripts/setup_github_actions.py."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), CONNECT_SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def can_manage(token_file: Path | None) -> bool:
    """True when this login may change a video's privacy (MANAGE_SCOPE or full youtube)."""
    import json as _json

    try:
        scopes = set(_json.loads(Path(token_file).read_text(encoding="utf-8")).get("scopes") or [])
    except Exception:
        return False
    return bool(scopes & {MANAGE_SCOPE, "https://www.googleapis.com/auth/youtube"})


def _youtube(client_secret_file: Path | None = None, token_file: Path | None = None):
    return build("youtube", "v3", credentials=_credentials(client_secret_file, token_file))


def set_thumbnail(video_id: str, thumbnail_path: Path, attempts: int = 4,
                  client_secret_file: Path | None = None, token_file: Path | None = None) -> None:
    youtube = _youtube(client_secret_file, token_file)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
            ).execute()
            return
        except Exception as exc:
            last_error = exc
            # Daily quota errors cannot recover seconds later. The queue retries later.
            if isinstance(exc, HttpError):
                reason = str(exc).lower()
                if (
                    "quotaexceeded" in reason
                    or ("exceeded your" in reason and "quota" in reason)
                    or "doesn't have permissions to upload and set custom video thumbnails" in reason
                    # Too many thumbnails on this channel today: retrying seconds
                    # later only spends more of the day's allowance.
                    or "uploadratelimitexceeded" in reason
                    or "too many thumbnails" in reason
                ):
                    break
            if attempt < attempts:
                time.sleep(8 * attempt)
    raise RuntimeError(f"Thumbnail upload failed after {attempts} attempts: {last_error}")


def upload_video(video_path: Path, thumbnail_path: Path, metadata: dict[str, object],
                 channel=None, publish_at: datetime | None = None,
                 progress_callback: Callable[[int], None] | None = None,
                 upload_thumbnail: bool = True) -> str:
    # Resolve per-channel credentials + settings; default = original kids behavior.
    if channel is not None:
        client_secret_file = channel.client_secret_path
        token_file = channel.token_path
        category_id = channel.category_id
        made_for_kids = channel.made_for_kids
        privacy = channel.privacy
    else:
        client_secret_file = None
        token_file = None
        category_id = "27"
        made_for_kids = True
        privacy = settings.youtube_privacy_status

    status_body: dict[str, object] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": made_for_kids,
    }
    # Scheduled publish: YouTube requires the video be private until publishAt,
    # then it flips it public automatically at that timestamp (RFC3339 UTC).
    if publish_at is not None:
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    # No video goes up without a checked thumbnail. It is uploaded private and
    # only scheduled / made public once its thumbnail is on (see release_video).
    from .thumbnail_check import ThumbnailNotReady, check_thumbnail, thumbnail_required

    required = thumbnail_required()
    final_status = status_body
    if required:
        if not upload_thumbnail:
            raise ThumbnailNotReady(
                "YouTube does not allow custom thumbnails on this channel yet. Verify it at "
                "youtube.com/verify, then press 'Thumbnails Are Verified' on the dashboard"
            )
        check = check_thumbnail(thumbnail_path)
        if not check.ok:
            raise ThumbnailNotReady(f"thumbnail failed its check: {check.summary}")
        if can_manage(token_file):
            # Up private, thumbnail, then released (scheduled / public).
            status_body = {"privacyStatus": "private", "selfDeclaredMadeForKids": made_for_kids}
        else:
            # This login cannot change privacy later, so a held video could never
            # be released. Upload it already scheduled (private until then) and
            # set the thumbnail right away; publishAt is at least an hour ahead,
            # which leaves the end-of-run thumbnail pass time to retry.
            if "publishAt" not in final_status:
                final_status = {**final_status, "privacyStatus": "private",
                                "publishAt": (datetime.now(timezone.utc) + timedelta(hours=1))
                                .isoformat().replace("+00:00", "Z")}
            status_body = final_status
            print("[upload] this YouTube login cannot change privacy; uploading scheduled. "
                  "Reconnect the channel on the dashboard to keep videos private until their thumbnail is on.")

    youtube = _youtube(client_secret_file, token_file)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": metadata["title"],
                "description": youtube_description(str(metadata["description"])),
                "tags": metadata["tags"],
                "categoryId": category_id,
                # Tells YouTube which language the title and the voice are in.
                "defaultLanguage": str(metadata.get("language") or "en"),
                "defaultAudioLanguage": str(metadata.get("language") or "en"),
            },
            "status": status_body,
        },
        media_body=MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    if progress_callback:
        progress_callback(0)
    while response is None:
        status, response = request.next_chunk()
        if status is not None and progress_callback:
            progress_callback(max(1, min(99, int(status.progress() * 100))))
    if progress_callback:
        progress_callback(100)
    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    remember_uploaded_title(token_file, str(metadata["title"]), video_url)

    if upload_thumbnail:
        try:
            set_thumbnail(video_id, thumbnail_path, client_secret_file=client_secret_file, token_file=token_file)
        except Exception as exc:
            held = " (video kept private until its thumbnail is set)" if required else ""
            raise ThumbnailUploadError(video_url, f"{exc}{held}") from exc
    if required and final_status != status_body:
        try:
            _set_status(youtube, video_id, final_status)
        except Exception as exc:
            raise ThumbnailUploadError(
                video_url, f"thumbnail is set, but releasing the private video failed: {exc}"
            ) from exc
    return video_url


# ---------------------------------------------------------------------------
# Duplicate guard against the channel itself.
#
# The bot's own database is the first duplicate check, but a database can be
# lost or start blank (a new GitHub repo, a restored PC, a missing bot-state
# branch), and then the bot happily remakes topics that are already on the
# channel. Before every upload the channel's real upload list is read once per
# run (private and scheduled videos included, about 1 quota unit per 50 videos)
# and a video whose title matches one already there is not uploaded again.
# ---------------------------------------------------------------------------

_UPLOADED_TITLES: dict[str, dict[str, str]] = {}
_TITLE_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def normalize_title(title: str) -> str:
    """The part of a title that names the video: no '| Channel' suffix, no
    hashtags, no emoji or punctuation, lower case."""
    core = str(title or "").split("|", 1)[0]
    core = re.sub(r"#\S+", " ", core)
    return " ".join(_TITLE_WORD.findall(core.lower()))


def _titles_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    a, b = set(left.split()), set(right.split())
    # Same words in a different order or with one small word changed.
    return min(len(a), len(b)) >= 4 and len(a & b) / len(a | b) >= 0.85


def _token_key(token_file: Path | None) -> str:
    return str(Path(token_file or settings.youtube_token_file).resolve())


def channel_uploaded_titles(channel) -> dict[str, str]:
    """normalized title -> video URL for every upload on this channel."""
    token_file = channel.token_path if channel is not None else None
    key = _token_key(token_file)
    if key in _UPLOADED_TITLES:
        return _UPLOADED_TITLES[key]
    client_secret_file = channel.client_secret_path if channel is not None else None
    youtube = _youtube(client_secret_file, token_file)
    items = youtube.channels().list(part="contentDetails", mine=True).execute().get("items") or []
    titles: dict[str, str] = {}
    if items:
        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        page_token = None
        while True:
            page = youtube.playlistItems().list(
                part="snippet", playlistId=playlist, maxResults=50, pageToken=page_token,
            ).execute()
            for item in page.get("items") or []:
                snippet = item.get("snippet") or {}
                video_id = (snippet.get("resourceId") or {}).get("videoId")
                normalized = normalize_title(snippet.get("title", ""))
                if video_id and normalized:
                    titles.setdefault(normalized, f"https://www.youtube.com/watch?v={video_id}")
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    _UPLOADED_TITLES[key] = titles
    print(f"[duplicate-check] {getattr(channel, 'id', 'default')}: {len(titles)} videos already on YouTube")
    return titles


def remember_uploaded_title(token_file: Path | None, title: str, video_url: str) -> None:
    """Add a fresh upload to the cached list so the same run cannot repeat it."""
    cached = _UPLOADED_TITLES.get(_token_key(token_file))
    normalized = normalize_title(title)
    if cached is not None and normalized:
        cached.setdefault(normalized, video_url)


def find_youtube_title_duplicate(channel, title: str) -> str | None:
    """URL of a video on the channel with the same title, or None.

    If YouTube cannot be read (quota, network) the upload is not blocked: the
    database checks still ran, and a missed upload costs more than a rare repeat."""
    wanted = normalize_title(title)
    if not wanted:
        return None
    try:
        titles = channel_uploaded_titles(channel)
    except Exception as exc:
        print(f"[duplicate-check] could not read the channel's uploads, not checked: {exc}")
        return None
    if wanted in titles:
        return titles[wanted]
    for existing, url in titles.items():
        if _titles_match(wanted, existing):
            return url
    return None


def _set_status(youtube, video_id: str, status: dict[str, object]) -> None:
    youtube.videos().update(part="status", body={"id": video_id, "status": status}).execute()


def release_video(video_url: str, channel, publish_at: str | datetime | None) -> datetime | None:
    """Schedule or publish a video that was held private until its thumbnail was set.

    Returns the publish time when it is scheduled, or None when it went live now.
    """
    from urllib.parse import parse_qs, urlparse

    video_id = (parse_qs(urlparse(video_url).query).get("v") or [video_url.rsplit("/", 1)[-1]])[0]
    when = publish_at
    if isinstance(when, str) and when:
        when = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if isinstance(when, datetime) and when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if not can_manage(channel.token_path):
        raise RuntimeError("this YouTube login cannot change a video's privacy: reconnect the channel on the "
                           "dashboard (Connect & verify) to give the bot that permission")
    status: dict[str, object] = {"selfDeclaredMadeForKids": bool(channel.made_for_kids)}
    # publishAt must lie ahead; a slot that passed while the video waited goes live now.
    if isinstance(when, datetime) and when > datetime.now(timezone.utc) + timedelta(minutes=10):
        status["privacyStatus"] = "private"
        status["publishAt"] = when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        when = None
        status["privacyStatus"] = channel.privacy
    _set_status(_youtube(channel.client_secret_path, channel.token_path), video_id, status)
    return when


def connect_and_verify(client_secret_file, token_file) -> str:
    """Authorize one channel and return the connected YouTube channel's name.

    Powers the dashboard 'Connect & verify' button so you can confirm each
    channel is linked to the CORRECT YouTube channel before any upload.
    """
    service = _youtube(client_secret_file, token_file)
    resp = service.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return "Connected, but no YouTube channel found on this account."
    return items[0]["snippet"]["title"]
