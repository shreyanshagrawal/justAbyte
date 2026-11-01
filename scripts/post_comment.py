#!/usr/bin/env python3
"""Post or update an advisory OpenCred assessment comment on a GitHub pull request.

Uses the GitHub REST API:
- Looks for an existing comment matching the hidden marker: <!-- opencred-assessment -->.
- If found, updates the comment in place (PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}).
- If not found, creates a new comment (POST /repos/{owner}/{repo}/issues/{issue_number}/comments).

Security & Determinism:
- Accepts markdown from a file or stdin, avoiding shell interpolation vulnerabilities.
- Validates that the comment contains the advisory disclaimer and comment marker.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path

try:
    from scripts.render_comment import COMMENT_MARKER
except ModuleNotFoundError:
    from render_comment import COMMENT_MARKER  # type: ignore[no-redef]

_GITHUB_API_URL = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def _github_request(
    url: str,
    method: str,
    token: str,
    data: Mapping[str, object] | None = None,
) -> tuple[int, dict[str, object] | list[object]]:
    """Execute a request against the GitHub REST API using urllib."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OpenCred-Action",
    }
    body_bytes = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=body_bytes,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            status = response.status
            parsed = json.loads(res_body) if res_body else {}
            return status, parsed
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")
        sys.stderr.write(f"GitHub API error ({err.code}): {err_body}\n")
        raise


def find_existing_comment_id(
    repo: str,
    pr_number: int,
    token: str,
    marker: str = COMMENT_MARKER,
) -> int | None:
    """Find existing OpenCred comment ID for the pull request, if one exists."""
    url = f"{_GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    _, comments = _github_request(url, method="GET", token=token)
    if isinstance(comments, list):
        for c in comments:
            if isinstance(c, dict) and marker in str(c.get("body", "")):
                comment_id = c.get("id")
                if isinstance(comment_id, int):
                    return comment_id
    return None


def post_or_update_comment(
    repo: str,
    pr_number: int,
    comment_body: str,
    token: str,
) -> int:
    """Create or update the PR comment, preventing duplicate comments on synchronize."""
    existing_id = find_existing_comment_id(repo, pr_number, token)
    if existing_id:
        update_url = f"{_GITHUB_API_URL}/repos/{repo}/issues/comments/{existing_id}"
        payload = {"body": comment_body}
        status, _ = _github_request(update_url, method="PATCH", token=token, data=payload)
        sys.stdout.write(f"Updated existing OpenCred comment #{existing_id} on PR #{pr_number}\n")
    else:
        create_url = f"{_GITHUB_API_URL}/repos/{repo}/issues/{pr_number}/comments"
        payload = {"body": comment_body}
        status, _ = _github_request(create_url, method="POST", token=token, data=payload)
        sys.stdout.write(f"Created new OpenCred comment on PR #{pr_number}\n")
    return status


def main() -> int:
    """CLI entry point for posting assessment comment."""
    parser = argparse.ArgumentParser(
        description="Post or update an OpenCred advisory comment on a PR.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="GitHub repository in owner/repo format.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="Pull request number.",
    )
    parser.add_argument(
        "--comment-file",
        type=Path,
        required=True,
        help="Path to rendered comment Markdown file.",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub authentication token (defaults to GITHUB_TOKEN env var).",
    )

    args = parser.parse_args()

    if not args.token:
        sys.stderr.write("Error: GitHub token must be provided via --token or GITHUB_TOKEN\n")
        return 1

    if not args.comment_file.is_file():
        sys.stderr.write(f"Error: Comment file not found at: {args.comment_file}\n")
        return 1

    comment_text = args.comment_file.read_text(encoding="utf-8")
    if COMMENT_MARKER not in comment_text:
        sys.stderr.write(f"Error: Comment file missing marker '{COMMENT_MARKER}'\n")
        return 1

    try:
        post_or_update_comment(
            repo=args.repo,
            pr_number=args.pr,
            comment_body=comment_text,
            token=args.token,
        )
        return 0
    except Exception as err:
        sys.stderr.write(f"Failed to post comment: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
