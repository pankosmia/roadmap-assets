#!/usr/bin/env python3
"""Delete the images that no issue, pull request or comment of the organization links to any more.

Images are uploaded by the roadmap dashboard as YYYY/MM/<uuid>.<ext>. A file is an orphan when its uuid
appears in no public issue/PR body or comment of the organization and it was added more than GRACE_DAYS ago
(the grace period covers images uploaded in a draft that is not posted yet).

The script only removes the files from the working tree (git rm); the workflow commits and pushes.
It deletes nothing, and fails, when the scan is incomplete or when it would remove more than MAX_DELETE files.
Environment: GH_TOKEN, ORG (default pankosmia), GRACE_DAYS (default 30), MAX_DELETE (default 100), DELETE (true to delete).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
ORG = os.environ.get("ORG", "pankosmia")
GRACE_DAYS = int(os.environ.get("GRACE_DAYS", "30"))
MAX_DELETE = int(os.environ.get("MAX_DELETE", "100"))
DELETE = os.environ.get("DELETE", "false").lower() == "true"
TOKEN = os.environ["GH_TOKEN"]

IMAGE_PATH = re.compile(r"^\d{4}/\d{2}/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(?:png|jpg|gif|webp)$")
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
REFERENCE = re.compile(rf"roadmap-assets/[^\s)\"'<>]*?({UUID})\.(?:png|jpg|gif|webp)", re.IGNORECASE)


class ScanError(Exception):
    pass


def request(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response), response.headers.get("Link", "")
        except urllib.error.HTTPError as error:
            if error.code in (502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise ScanError(f"GitHub answered {error.code} for {url}: {error.read().decode()[:200]}")
        except urllib.error.URLError as error:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise ScanError(f"Could not reach {url}: {error}")


def pages(url):
    while url:
        data, link = request(url)
        yield from data
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = match.group(1) if match else None


def referenced_uuids():
    found = set()
    texts = 0
    repos = [repo["name"] for repo in pages(f"{API}/orgs/{ORG}/repos?type=public&per_page=100") if not repo["archived"]]
    for name in repos:
        base = f"{API}/repos/{ORG}/{name}"
        for item in pages(f"{base}/issues?state=all&per_page=100"):
            texts += 1
            found.update(match.lower() for match in REFERENCE.findall(item.get("body") or ""))
        for comment in pages(f"{base}/issues/comments?per_page=100"):
            texts += 1
            found.update(match.lower() for match in REFERENCE.findall(comment.get("body") or ""))
    print(f"Scanned {len(repos)} repositories, {texts} issues, pull requests and comments: {len(found)} images referenced.")
    if not repos or texts == 0:
        raise ScanError("The scan found nothing at all, which is not plausible: refusing to delete anything.")
    return found


def tracked_images():
    # One pass over the history: the commit time of the commit that added each image.
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--name-only", "--format=@%ct"],
        check=True, capture_output=True, text=True,
    ).stdout
    added = {}
    stamp = 0
    for line in log.splitlines():
        if line.startswith("@"):
            stamp = int(line[1:])
        elif IMAGE_PATH.match(line):
            added.setdefault(line, stamp)
    existing = set(subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout.splitlines())
    return {path: stamp for path, stamp in added.items() if path in existing}


def summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as handle:
            handle.write("\n".join(lines) + "\n")


def main():
    images = tracked_images()
    referenced = referenced_uuids()
    cutoff = time.time() - GRACE_DAYS * 86400
    orphans = sorted(
        path for path, stamp in images.items()
        if IMAGE_PATH.match(path).group(1) not in referenced and stamp < cutoff
    )
    recent = sum(1 for path, stamp in images.items() if IMAGE_PATH.match(path).group(1) not in referenced and stamp >= cutoff)
    print(f"{len(images)} images, {len(orphans)} orphans older than {GRACE_DAYS} days, {recent} unreferenced but within the grace period.")
    summary([
        "## Orphan images",
        f"- Images: {len(images)}",
        f"- Orphans older than {GRACE_DAYS} days: {len(orphans)}",
        f"- Unreferenced, within the grace period: {recent}",
        f"- Mode: {'delete' if DELETE else 'dry run'}",
        *[f"  - `{path}`" for path in orphans[:200]],
    ])
    if len(orphans) > MAX_DELETE:
        raise ScanError(f"{len(orphans)} orphans is more than MAX_DELETE ({MAX_DELETE}): check the list, then raise the limit.")
    if not DELETE:
        print("Dry run: nothing deleted. Run the workflow with delete enabled to remove them.")
        return
    for start in range(0, len(orphans), 100):
        subprocess.run(["git", "rm", "-q", "--", *orphans[start:start + 100]], check=True)
    print(f"Removed {len(orphans)} files from the working tree.")


if __name__ == "__main__":
    try:
        main()
    except ScanError as error:
        print(f"::error::{error}")
        sys.exit(1)
