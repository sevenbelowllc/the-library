"""Sandbox smoke: create one PARKLOT ticket with rich markdown to visually
confirm ADF rendering. Run with the-library venv active."""

from __future__ import annotations

import asyncio
import sys

from library_server.pm.jira_client import JiraClient

SITE = "https://sevenbelow.atlassian.net"
PROJECT = "PARKLOT"

SAMPLE_MD = """# md_to_adf smoke test

This ticket is a **smoke test** of the new markdown→ADF converter shipped in
`the-library/src/library_server/pm/md_to_adf.py`. If the formatting below
renders properly in Jira, the fix works.

## Inline marks

Bold (`**bold**`): **bold** · Italic (`*italic*`): *italic* · Code: `inline_code()` ·
[link to spec](https://github.com/sevenbelowllc/the-library) · ~~strike~~.

## Bullet list

- first bullet
- second bullet with `code`
- third bullet with [link](https://example.com)

## Ordered list

1. step one
2. step two
3. step three

## Code block

```python
def md_to_adf(text: str) -> dict:
    return parse(text)
```

## Blockquote

> Every Class T table must have RLS FORCEd and a fail-closed predicate.

## Horizontal rule

---

## Table

| Field | Required | Note |
|-------|----------|------|
| summary | yes | short |
| description | yes | now markdown-rendered |
| labels | no | array |

End of smoke.
"""


async def main() -> int:
    client = JiraClient(site_url=SITE)
    issue = await client.create_issue(
        project_key=PROJECT,
        issue_type="Task",
        summary="md_to_adf smoke — confirm rich rendering",
        description=SAMPLE_MD,
        labels=["md-adf-smoke"],
    )
    print(f"Created: {SITE}/browse/{issue.get('key')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
