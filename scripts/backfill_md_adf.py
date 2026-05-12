"""Backfill: scan Jira projects for tickets whose description was shipped
as a single-paragraph ADF containing raw markdown chars, and re-emit them
via the fixed md_to_adf converter.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/backfill_md_adf.py --dry-run [--key PARKLOT-78]
    PYTHONPATH=src .venv/bin/python scripts/backfill_md_adf.py --apply [--project PARKLOT]

Default projects: DEIOCAP, COS, PARKLOT, LIBRARY.

Detection rule (broken shape):
  description.content has exactly one paragraph node whose only child is a
  single `text` node, AND that text contains any markdown signal char
  (#, **, *, _, `, >, ``` , [, |, ---) OR a newline.

Idempotency:
  - If re-emitted ADF == current ADF, no PUT is sent.
  - Already-rich descriptions (multi-block, marks, lists, tables) match no
    broken-shape filter and are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from library_server.pm.jira_client import JiraClient
from library_server.pm.md_to_adf import md_to_adf

SITE = "https://sevenbelow.atlassian.net"
DEFAULT_PROJECTS = ["DEIOCAP", "COS", "PARKLOT", "LIBRARY"]

MD_SIGNAL = re.compile(r"(^|\n)\s*(#{1,6} |[-*+] |\d+\. |> |```)|\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\n", re.MULTILINE)


def is_broken_shape(desc: dict[str, Any] | None) -> tuple[bool, str]:
    """Return (is_broken, raw_text). Raw text is the markdown to re-render."""
    if not desc or desc.get("type") != "doc":
        return (False, "")
    content = desc.get("content") or []
    if len(content) != 1:
        return (False, "")
    node = content[0]
    if node.get("type") != "paragraph":
        return (False, "")
    children = node.get("content") or []
    if len(children) != 1:
        return (False, "")
    child = children[0]
    if child.get("type") != "text" or child.get("marks"):
        return (False, "")
    text = child.get("text") or ""
    if not text:
        return (False, "")
    if MD_SIGNAL.search(text):
        return (True, text)
    return (False, "")


async def scan_project(client: JiraClient, project_key: str) -> list[dict[str, Any]]:
    """Return list of issues with summary + description (paginated)."""
    issues: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        params: dict[str, Any] = {
            "jql": f"project = {project_key} ORDER BY created DESC",
            "fields": ["summary", "description"],
            "maxResults": 100,
        }
        if next_token:
            params["nextPageToken"] = next_token
        page = await client._request("POST", "/rest/api/3/search/jql", json=params)
        for issue in page.get("issues", []):
            issues.append(issue)
        next_token = page.get("nextPageToken")
        if not next_token or page.get("isLast"):
            break
    return issues


async def repair_issue(
    client: JiraClient,
    issue: dict[str, Any],
    apply: bool,
) -> tuple[str, str]:
    """Return (status, key). status ∈ {repaired, dry-run, skipped, identical}."""
    key = issue.get("key", "?")
    desc = issue.get("fields", {}).get("description")
    broken, raw_text = is_broken_shape(desc)
    if not broken:
        return ("skipped", key)
    new_adf = md_to_adf(raw_text)
    if new_adf == desc:
        return ("identical", key)
    if not apply:
        return ("dry-run", key)
    await client._request(
        "PUT",
        f"/rest/api/3/issue/{key}",
        json={"fields": {"description": new_adf}},
    )
    return ("repaired", key)


async def repair_comments(
    client: JiraClient,
    issue_key: str,
    apply: bool,
) -> dict[str, int]:
    """Walk all comments on an issue; repair broken-shape bodies."""
    stats = {"repaired": 0, "dry-run": 0, "skipped": 0}
    start_at = 0
    while True:
        page = await client._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}/comment",
            params={"startAt": start_at, "maxResults": 100},
        )
        for comment in page.get("comments", []):
            comment_id = comment.get("id")
            body = comment.get("body")
            broken, raw_text = is_broken_shape(body)
            if not broken:
                stats["skipped"] += 1
                continue
            new_adf = md_to_adf(raw_text)
            if new_adf == body:
                stats["skipped"] += 1
                continue
            if not apply:
                stats["dry-run"] += 1
                continue
            await client._request(
                "PUT",
                f"/rest/api/3/issue/{issue_key}/comment/{comment_id}",
                json={"body": new_adf},
            )
            stats["repaired"] += 1
        total = page.get("total", 0)
        start_at += len(page.get("comments", []))
        if start_at >= total or not page.get("comments"):
            break
    return stats


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", action="store_true", help="Actually write changes")
    ap.add_argument("--project", action="append", help="Limit to one or more projects")
    ap.add_argument("--key", help="Process a single ticket key (e.g. PARKLOT-78)")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N tickets (0 = no limit)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--comments", action="store_true", help="Also repair comment bodies")
    ap.add_argument("--comments-only", action="store_true", help="Skip descriptions; repair only comments")
    ap.add_argument("--concurrency", type=int, default=1, help="Parallel issue workers (8 recommended for full apply)")
    args = ap.parse_args()
    apply = args.apply
    projects = args.project or DEFAULT_PROJECTS
    do_descriptions = not args.comments_only
    do_comments = args.comments or args.comments_only

    client = JiraClient(site_url=SITE)

    if args.key:
        issue = await client.get_issue(args.key, fields="summary,description")
        issue_with_key = {"key": args.key, "fields": issue.get("fields", {})}
        if do_descriptions:
            status, _ = await repair_issue(client, issue_with_key, apply)
            print(f"{args.key} description: {status}")
        if do_comments:
            cstats = await repair_comments(client, args.key, apply)
            print(f"{args.key} comments: {cstats}")
        if args.verbose:
            broken, raw = is_broken_shape(issue.get("fields", {}).get("description"))
            print(f"  broken={broken} raw_chars={len(raw)}")
        return 0

    totals = {"repaired": 0, "dry-run": 0, "skipped": 0, "identical": 0}
    ctotals = {"repaired": 0, "dry-run": 0, "skipped": 0}
    sem = asyncio.Semaphore(max(1, args.concurrency))
    lock = asyncio.Lock()
    processed = [0]

    errors: list[str] = []

    async def handle_one(issue: dict[str, Any]) -> None:
        async with sem:
            key = issue.get("key", "?")
            if do_descriptions:
                try:
                    status, _ = await repair_issue(client, issue, apply)
                    async with lock:
                        totals[status] += 1
                        if status in ("repaired", "dry-run"):
                            print(f"  desc {status:9} {key}")
                        elif args.verbose:
                            print(f"  desc {status:9} {key}")
                except Exception as e:
                    async with lock:
                        errors.append(f"desc {key}: {e}")
                        print(f"  desc ERROR    {key}: {e}")
            if do_comments:
                try:
                    cstats = await repair_comments(client, key, apply)
                    async with lock:
                        for k, v in cstats.items():
                            ctotals[k] += v
                        if cstats["repaired"] or cstats["dry-run"]:
                            print(f"  cmts {cstats} {key}")
                except Exception as e:
                    async with lock:
                        errors.append(f"cmts {key}: {e}")
                        print(f"  cmts ERROR    {key}: {e}")
            async with lock:
                processed[0] += 1

    for project in projects:
        print(f"\n=== Scanning {project} ===")
        issues = await scan_project(client, project)
        print(f"  {len(issues)} issues (concurrency={args.concurrency})")
        batch = issues
        if args.limit:
            remaining = max(0, args.limit - processed[0])
            batch = issues[:remaining]
            if not batch:
                break
        await asyncio.gather(*(handle_one(issue) for issue in batch))
        if args.limit and processed[0] >= args.limit:
            break

    print("\n=== Descriptions ===")
    for k, v in totals.items():
        print(f"  {k}: {v}")
    if do_comments:
        print("\n=== Comments ===")
        for k, v in ctotals.items():
            print(f"  {k}: {v}")
    if errors:
        print(f"\n=== Errors ({len(errors)}) ===")
        for e in errors[:50]:
            print(f"  {e}")
        if len(errors) > 50:
            print(f"  ... {len(errors)-50} more")
    print(f"\nMode: {'APPLY' if apply else 'DRY-RUN (use --apply to write)'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
