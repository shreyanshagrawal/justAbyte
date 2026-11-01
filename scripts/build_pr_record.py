#!/usr/bin/env python3
"""Build an OpenCred PullRequestRecord JSON from GitHub event payload and git diff.

This script parses:
- GITHUB_EVENT_PATH (or an explicit event payload JSON file)
- A diff text file generated from git diff between base and PR head

It extracts only safe metadata fields and normalizes the diff according to
OpenCred's deterministic fingerprinting rules. No untrusted code is executed.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from opencred.core.fingerprint import normalize_diff
from opencred.core.models import PullRequestRecord, to_canonical_json

_ISSUE_REF_RE = re.compile(
    r"(?:(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+)?#([0-9]+)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>\"'()]+", re.IGNORECASE)


def extract_issue_numbers(text: str) -> list[int]:
    """Extract referenced GitHub issue numbers from text in sorted order."""
    matches = _ISSUE_REF_RE.findall(text)
    numbers = {int(m) for m in matches if int(m) > 0}
    return sorted(numbers)


def extract_external_links(text: str) -> list[str]:
    """Extract external HTTP/HTTPS links from text in sorted order."""
    matches = _URL_RE.findall(text)
    clean_urls = {url.rstrip(".,;:)") for url in matches if url.strip()}
    return sorted(clean_urls)


def build_pr_record(
    event_payload: dict[str, Any],
    diff_text: str,
    changed_files: list[str] | None = None,
) -> PullRequestRecord:
    """Build a PullRequestRecord from GitHub pull_request event payload and diff text.

    Args:
        event_payload: Parsed GitHub Actions event JSON dictionary.
        diff_text: Raw diff text between base commit and PR head.
        changed_files: Optional list of changed relative file paths. If not provided,
            changed files are discovered from the git diff hunk headers.

    Returns:
        Validated immutable PullRequestRecord instance.
    """
    pr_data = event_payload.get("pull_request")
    if not pr_data or not isinstance(pr_data, dict):
        raise ValueError("GitHub event payload missing 'pull_request' object")

    repository = event_payload.get("repository", {})
    repo_full_name = repository.get("full_name") or pr_data.get("base", {}).get("repo", {}).get(
        "full_name"
    )
    if not repo_full_name:
        raise ValueError("Could not determine repository full_name from event payload")

    pr_number = pr_data.get("number")
    if pr_number is None or int(pr_number) < 1:
        raise ValueError(f"Invalid pull request number: {pr_number}")

    author = pr_data.get("user", {}).get("login", "")
    if not author:
        raise ValueError("Missing pull request author login in event payload")

    opened_at = pr_data.get("created_at")
    if not opened_at:
        raise ValueError("Missing pull request created_at timestamp in event payload")

    title = pr_data.get("title") or ""
    body = pr_data.get("body") or ""

    # Parse changed files from diff headers if not explicitly supplied
    if changed_files is None:
        files_set: set[str] = set()
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                filepath = line[6:].strip()
                if filepath and filepath != "/dev/null":
                    files_set.add(filepath)
            elif line.startswith("--- a/"):
                filepath = line[6:].strip()
                if filepath and filepath != "/dev/null":
                    files_set.add(filepath)
        final_files = sorted(files_set)
    else:
        final_files = sorted(set(changed_files))

    combined_text = f"{title}\n{body}"
    linked_issues = extract_issue_numbers(combined_text)
    external_links = extract_external_links(combined_text)
    normalized_diff_content = normalize_diff(diff_text)

    return PullRequestRecord(
        repo=repo_full_name,
        number=int(pr_number),
        author=author,
        opened_at=opened_at,
        title=title,
        body=body,
        changed_files=final_files,
        normalized_diff=normalized_diff_content,
        linked_issue_numbers=linked_issues,
        external_links=external_links,
    )


def main() -> int:
    """Parse arguments and write the PullRequestRecord canonical JSON."""
    parser = argparse.ArgumentParser(
        description="Construct an OpenCred PullRequestRecord JSON from event payload and diff.",
    )
    parser.add_argument(
        "--event",
        type=Path,
        required=True,
        help="Path to GitHub event payload JSON file (e.g. $GITHUB_EVENT_PATH).",
    )
    parser.add_argument(
        "--diff",
        type=Path,
        required=True,
        help="Path to unified diff text file generated between base and head.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output destination path for the PullRequestRecord JSON.",
    )

    args = parser.parse_args()

    if not args.event.is_file():
        sys.stderr.write(f"Error: Event payload file not found: {args.event}\n")
        return 1

    if not args.diff.is_file():
        sys.stderr.write(f"Error: Diff file not found: {args.diff}\n")
        return 1

    try:
        event_data = json.loads(args.event.read_text(encoding="utf-8"))
        diff_text = args.diff.read_text(encoding="utf-8")
        pr_record = build_pr_record(event_data, diff_text)
    except Exception as err:
        sys.stderr.write(f"Error building PullRequestRecord: {err}\n")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    canonical_json = to_canonical_json(pr_record) + "\n"
    args.out.write_text(canonical_json, encoding="utf-8")
    sys.stdout.write(f"Successfully generated PullRequestRecord JSON -> {args.out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
