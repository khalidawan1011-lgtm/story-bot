# Bot API

Story Bot has an HTTP API so other bots (for example an SEO / keyword bot) can
read and manage it, and it can connect to other bots' APIs. Both are managed on
the dashboard's **Bot API** tab. Code: `src/bot_api.py`.

## Connecting two bots

1. On Story Bot: **Bot API → Create API key**, name it after the other bot
   (`seo-bot`), tick `read` and, if it may change things, `write`, and tick the
   channels it may use (or **All channels**, which includes channels added
   later). Copy the key; it is shown once. The channels of a key can be changed
   later on the same tab.
2. In the other bot: save Story Bot's address (`http://127.0.0.1:8000`) and that key.
3. The other bot creates a key for Story Bot the same way.
4. On Story Bot: **Bot API → Connected bots → Add & test** with the other bot's
   address and key. The test calls `GET /api/v1` and `GET /api/v1/status`.

The dashboard listens on 127.0.0.1, so both bots must run on the same PC. For a
bot on another machine, put the dashboard behind a tunnel (e.g. Cloudflare
Tunnel) and use its https address.

## Authentication

Every request except `GET /api/v1` needs:

```
Authorization: Bearer sbk_...
```

| Answer | Meaning |
|---|---|
| 401 | no key, wrong key, or revoked key |
| 403 | the key lacks the permission (`read` / `write`) |
| 404 | unknown channel, or a channel this key was not given (it is not even listed) |

Only a SHA-256 hash of each key is stored (`data/api_keys.json`, not in git).
Revoking a key on the dashboard cuts the bot off at once.

## Endpoints

| Method | Path | Permission | Body / query | Answer |
|---|---|---|---|---|
| GET | `/api/v1` | none | | bot name, API version, endpoint list |
| GET | `/api/v1/status` | read | | time, channel count, running jobs |
| GET | `/api/v1/channels` | read | | every channel: uploads today and limit, YouTube accounts, Facebook/TikTok status |
| GET | `/api/v1/channels/<id>` | read | | one channel plus its YouTube analytics snapshot |
| GET | `/api/v1/channels/<id>/videos` | read | `?limit=50&type=short\|long` | videos: title, topic, status, `youtube_id`, publish time |
| GET | `/api/v1/channels/<id>/topics` | read | | topic bank: key and title |
| POST | `/api/v1/channels/<id>/topics` | write | `{"topics": ["keyword idea", ...], "make_video": false, "upload": true}` (max 10) | 202 + `job_id`; writes a script per topic, and builds the video if `make_video` |
| POST | `/api/v1/channels/<id>/generate` | write | `{"shorts": 1-4, "upload": true}` | 202 + `job_id` |
| POST | `/api/v1/channels/<id>/videos/<youtube_id>/seo` | write | `{"title": "...", "description": "...", "tags": ["..."]}` (any of them) | changes the video on YouTube; other fields are kept |
| GET | `/api/v1/jobs/<job_id>` | read | | `queued` / `running` / `done` / `error` and detail |

Rules checked before an SEO change: the channel's YouTube login must be allowed
to edit videos, the video must be on that same channel, title 1-100 characters
without `<` `>`, tags at most 500 characters together.

## Examples

```bash
KEY=sbk_...
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:8000/api/v1/channels

curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"topics": ["why octopuses have three hearts"], "make_video": true}' \
     http://127.0.0.1:8000/api/v1/channels/pondermals/topics

curl -X POST -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"title": "Why Octopuses Have 3 Hearts 🐙 | Pondermals", "tags": ["octopus facts", "animal facts"]}' \
     http://127.0.0.1:8000/api/v1/channels/pondermals/videos/VIDEO_ID/seo
```

From Story Bot's own code, calling a connected bot:

```python
from src import bot_api
bot_api.call("seo-bot", "GET", "/api/v1/status")
bot_api.call("seo-bot", "POST", "/api/v1/keywords", {"topic": "animal facts"})
```

## For the other bot

To be connectable the other bot only needs:

- `GET /api/v1` without a key, answering JSON with `"bot"` (its name) and `"api": 1`;
- `GET /api/v1/status` that accepts `Authorization: Bearer <key>` and answers JSON;
- its own endpoints (keywords, SEO suggestions, ...) under `/api/v1/`.
