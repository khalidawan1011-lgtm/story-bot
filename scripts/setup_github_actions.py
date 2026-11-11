"""One-time setup so GitHub can run the daily videos without this PC.

Reads the private files on this machine (.env, OAuth clients, YouTube tokens),
packs them, and hands them to `gh secret set` through a pipe — the values are
never printed and never touch shell history.

    .venv\\Scripts\\python.exe scripts\\setup_github_actions.py

Re-run it whenever a token or key changes on this PC.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ci_secrets  # noqa: E402

SECRET_NAME = "BOT_SECRETS_B64"


def _gh() -> str:
    path = shutil.which("gh")
    if not path:
        raise SystemExit(
            "GitHub CLI is not installed. Get it from https://cli.github.com/ , "
            "then run:  gh auth login"
        )
    return path


def _check_auth(gh: str) -> None:
    # Ask for the active account only: `gh auth status` fails when ANY saved
    # account has a dead token (e.g. a suspended one), even if the active
    # account works.
    result = subprocess.run([gh, "api", "user", "-q", ".login"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit("Not signed in to GitHub. Run:  gh auth login")
    print(f"Signed in as {result.stdout.strip()}; secrets go to {_repo()}.\n")


def _repo() -> str:
    """owner/name of the `origin` remote. Named explicitly, because with a second
    remote (an old account kept as old-origin) gh refuses to guess."""
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if not match:
        raise SystemExit(f"The origin remote is not a GitHub repository: {url or '(none)'}")
    return match.group(1)


def main() -> None:
    gh = _gh()
    _check_auth(gh)

    files = [str(p.relative_to(ROOT)) for p in ci_secrets._collect()]
    if not files:
        raise SystemExit("No private files found — is this the project folder?")
    print("Packing these private files (contents are never shown):")
    for name in files:
        print(f"  - {name}")

    blob = ci_secrets.pack()
    print(f"\nUploading {len(blob) // 1024} KB to the repository secret {SECRET_NAME} ...")
    result = subprocess.run(
        [gh, "secret", "set", SECRET_NAME, "-R", _repo()],
        input=blob, text=True, cwd=ROOT, capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"gh secret set failed:\n{result.stderr.strip()}")

    print("Done.\n")
    print("GitHub can now build and upload the daily videos on its own.")
    print("Start it by hand once to check:")
    print("  gh workflow run daily-videos.yml")
    print("Then watch it:")
    print("  gh run watch")


if __name__ == "__main__":
    main()
