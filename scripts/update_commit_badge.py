#!/usr/bin/env python3
"""Count a user's LegacyDroid commits and update the organization profile badge.

The workflow runs this script on a schedule. It intentionally discovers repositories
from the GitHub API instead of maintaining a hard-coded repository list.

Counting rules:
* Only repositories with the target branch (default: legacydroid-14) are included.
* Forks use a matching upstream branch when one can be found, so upstream commits do
  not get attributed to the LegacyDroid project.
* Non-forks use GitHub's author-filtered commit API.
* A missing target branch is a normal skip, which also supports future BoringDroid
  repositories that have not been brought into the Android 14 branch yet.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OWNER = os.environ.get("OWNER", "LegacyDroid")
TARGET_BRANCH = os.environ.get("TARGET_BRANCH", "legacydroid-14")
GITHUB_USER = os.environ.get("COMMIT_GITHUB_USER", "minhmc2007").strip()
AUTHOR_NAME = os.environ.get("COMMIT_AUTHOR_NAME", GITHUB_USER).strip()
AUTHOR_EMAIL = os.environ.get("COMMIT_AUTHOR_EMAIL", "").strip().lower()
README_PATH = Path(os.environ.get("README_PATH", "profile/README.md"))

START_MARKER = "<!-- LEGACYDROID_COMMIT_COUNT:START -->"
END_MARKER = "<!-- LEGACYDROID_COMMIT_COUNT:END -->"

# These are the Android 14 / LineageOS 21 branch names used by the current
# LegacyDroid tree. A fork is only compared when one of these exists upstream.
UPSTREAM_BRANCH_CANDIDATES = (
    TARGET_BRANCH,
    "lineage-21.0",
    "lineage-21",
)


class GitHubAPIError(RuntimeError):
    """An error returned by the GitHub API."""


class GitHubAPI:
    def __init__(self, api_url: str, token: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LegacyDroid-commit-badge",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        allow_404: bool = False,
    ) -> Any:
        query = ""
        if params:
            query = "?" + urlencode(params, doseq=True)
        url = f"{self.api_url}{path}{query}"
        request = Request(url, headers=self.headers, method="GET")

        for attempt in range(3):
            try:
                with urlopen(request, timeout=45) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                if error.code == 404 and allow_404:
                    return None
                if error.code >= 500 and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise GitHubAPIError(
                    f"GitHub API GET {path} returned HTTP {error.code}: {body[:300]}"
                ) from error
            except (URLError, TimeoutError) as error:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise GitHubAPIError(f"GitHub API GET {path} failed: {error}") from error

        raise GitHubAPIError(f"GitHub API GET {path} failed after retries")

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        item_key: str | None = None,
    ) -> Iterable[Any]:
        page = 1
        while True:
            page_params = dict(params or {})
            page_params.update({"per_page": 100, "page": page})
            data = self.get(path, page_params)
            values = data.get(item_key, []) if item_key else data
            if not isinstance(values, list):
                raise GitHubAPIError(f"Unexpected response while paginating {path}")
            yield from values
            if len(values) < 100:
                return
            page += 1


def repo_path(owner: str, repo: str, suffix: str = "") -> str:
    return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}{suffix}"


def is_mine(commit: dict[str, Any]) -> bool:
    """Return whether a REST commit object belongs to the configured user.

    The top-level author login is authoritative. The name/email fallback handles
    commits whose email is not linked to a GitHub account, without counting the
    committer of somebody else's commit.
    """

    linked_author = commit.get("author") or {}
    if (linked_author.get("login") or "").casefold() == GITHUB_USER.casefold():
        return True

    identity = ((commit.get("commit") or {}).get("author") or {})
    if (identity.get("name") or "").casefold() == AUTHOR_NAME.casefold():
        return True
    if AUTHOR_EMAIL and (identity.get("email") or "").casefold() == AUTHOR_EMAIL:
        return True
    return False


def find_upstream_branch(api: GitHubAPI, parent_full_name: str) -> tuple[str, str] | None:
    parent_owner, parent_repo = parent_full_name.split("/", 1)
    for branch in dict.fromkeys(UPSTREAM_BRANCH_CANDIDATES):
        result = api.get(
            repo_path(parent_owner, parent_repo, f"/branches/{quote(branch, safe='')}"),
            allow_404=True,
        )
        if result is not None:
            commit = result.get("commit") or {}
            sha = commit.get("sha")
            if sha:
                return branch, sha
    return None


def count_user_commits(
    api: GitHubAPI,
    repo: dict[str, Any],
) -> tuple[int, str, str | None]:
    name = repo["name"]

    # A missing branch is expected for repositories not used by the Android 14
    # build. This is also the desired behavior for BoringDroid repositories that
    # do not have a legacydroid-14 branch yet.
    if api.get(
        repo_path(OWNER, name, f"/branches/{quote(TARGET_BRANCH, safe='')}"),
        allow_404=True,
    ) is None:
        return 0, "skipped: no target branch", None

    parent = repo.get("parent") or {}
    parent_full_name = parent.get("full_name")

    # The organization repository-list endpoint does not include the full parent
    # object, so fetch details for forks when necessary.
    if repo.get("fork") and not parent_full_name:
        details = api.get(repo_path(OWNER, name))
        parent = details.get("parent") or details.get("source") or {}
        parent_full_name = parent.get("full_name")

    upstream_branch = None
    if repo.get("fork") and parent_full_name:
        upstream_branch = find_upstream_branch(api, parent_full_name)

    if upstream_branch:
        upstream_branch_name, upstream_sha = upstream_branch
        compare_path = repo_path(
            OWNER,
            name,
            f"/compare/{quote(upstream_sha, safe='')}...{quote(TARGET_BRANCH, safe='')}",
        )
        try:
            commits = api.paginate(compare_path, item_key="commits")
            count = sum(1 for commit in commits if is_mine(commit))
            return count, f"fork compared with {parent_full_name}:{upstream_branch_name}", upstream_branch_name
        except GitHubAPIError as error:
            # Some valid forks expose the upstream branch but GitHub cannot
            # compare those histories (usually because the fork was imported).
            # Fall back to the author-filtered branch history for those repos.
            print(f"WARN {name}: upstream compare failed; using author filter: {error}")

    commits = api.paginate(
        repo_path(OWNER, name, "/commits"),
        {"sha": TARGET_BRANCH, "author": GITHUB_USER},
    )
    count = sum(1 for commit in commits if is_mine(commit))
    return count, "author-filtered branch history", None


def badge_block(total: int) -> str:
    badge_url = (
        "https://img.shields.io/badge/"
        f"LegacyDroid%20commits-{total}-brightgreen?style=flat-square"
    )
    return (
        f"{START_MARKER}\n"
        f"[![LegacyDroid commits]({badge_url})]"
        f"(https://github.com/{OWNER})\n"
        f"{END_MARKER}"
    )


def update_readme(total: int) -> None:
    text = README_PATH.read_text(encoding="utf-8")
    replacement = badge_block(total)

    if START_MARKER in text and END_MARKER in text:
        start = text.index(START_MARKER)
        end = text.index(END_MARKER, start) + len(END_MARKER)
        updated = text[:start] + replacement + text[end:]
    else:
        # Keep the action useful even if the marker was removed manually.
        heading = re.search(r"^# .+?(?:\n|$)", text, flags=re.MULTILINE)
        position = heading.end() if heading else 0
        updated = text[:position] + "\n" + replacement + "\n" + text[position:]

    if updated != text:
        README_PATH.write_text(updated, encoding="utf-8")


def write_summary(rows: list[tuple[str, int, str]], skipped: list[str], total: int) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## LegacyDroid commit count",
        "",
        f"**{total}** commits by `{GITHUB_USER}` on `{TARGET_BRANCH}`.",
        "",
        "| Repository | Count | Method |",
        "|---|---:|---|",
    ]
    for name, count, method in rows:
        lines.append(f"| `{name}` | {count} | {method} |")
    if skipped:
        lines.extend(["", "Skipped without a target branch:", ""])
        lines.extend(f"- `{name}`" for name in sorted(skipped))
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not GITHUB_USER:
        print("COMMIT_GITHUB_USER must not be empty", file=sys.stderr)
        return 2
    if not TOKEN:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2

    api = GitHubAPI(API_URL, TOKEN)
    repos = list(
        api.paginate(
            f"/orgs/{quote(OWNER, safe='')}/repos",
            {"type": "all", "sort": "full_name"},
        )
    )

    counted: list[tuple[str, int, str]] = []
    skipped: list[str] = []
    errors: list[str] = []

    for repo in repos:
        name = repo.get("name", "")
        if not name:
            continue
        try:
            count, method, _ = count_user_commits(api, repo)
            if method.startswith("skipped"):
                skipped.append(name)
                print(f"SKIP {name}: {method}")
            else:
                counted.append((name, count, method))
                print(f"COUNT {name}: {count} ({method})")
        except GitHubAPIError as error:
            errors.append(f"{name}: {error}")

    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1

    total = sum(count for _, count, _ in counted)
    update_readme(total)
    write_summary(counted, skipped, total)
    print(f"TOTAL {total} across {len(counted)} repositories; skipped {len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
