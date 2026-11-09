"""Which GitHub account this bot sends its code, keys and daily runs to.

Read through the GitHub CLI (`gh api user`) and the repo's `origin` remote,
cached for 12 hours in data/github_identity.json so the dashboard stays fast.
"""
from __future__ import annotations

import json
import re
import subprocess
import time

from .config import settings

_CACHE = settings.root / "data" / "github_identity.json"
_MAX_AGE = 12 * 3600


def _run(*args: str) -> str:
    try:
        result = subprocess.run(list(args), cwd=settings.root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo() -> str:
    url = _run("git", "remote", "get-url", "origin")
    match = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else ""


def _lookup() -> dict:
    repo = _repo()
    info = {"repo": repo, "repo_url": f"https://github.com/{repo}" if repo else ""}
    raw = _run("gh", "api", "user")
    if not raw:
        info["error"] = "GitHub CLI is not signed in on this PC (run: gh auth login)."
        return info
    try:
        user = json.loads(raw)
    except ValueError:
        info["error"] = "GitHub CLI gave an unreadable answer."
        return info
    email = user.get("email") or ""
    if not email:
        # Only works when gh has the "user" scope; the public email is enough otherwise.
        try:
            emails = json.loads(_run("gh", "api", "user/emails") or "[]")
            email = next((e.get("email") for e in emails if e.get("primary")), "") or ""
        except ValueError:
            email = ""
    info.update({
        "login": user.get("login") or "",
        "name": user.get("name") or "",
        "email": email,
        "avatar": user.get("avatar_url") or "",
        "url": user.get("html_url") or "",
    })
    if repo and info["login"] and repo.split("/")[0].lower() != info["login"].lower():
        info["warning"] = f"gh is signed in as {info['login']}, but this bot's repo belongs to {repo.split('/')[0]}."
    return info


def identity(refresh: bool = False) -> dict:
    """{login, name, email, avatar, url, repo, repo_url[, warning, error]}."""
    if not refresh:
        try:
            cached = json.loads(_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("checked", 0)) < _MAX_AGE and not cached.get("error"):
                return cached
        except (OSError, ValueError):
            pass
    info = _lookup()
    info["checked"] = time.time()
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(info, indent=2), encoding="utf-8")
    except OSError:
        pass
    return info
