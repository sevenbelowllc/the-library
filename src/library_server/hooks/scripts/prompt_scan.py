"""UserPromptSubmit hook script for the MMU.

Invoked by Claude Code on each user prompt (UserPromptSubmit hook event).
Scans the prompt for domain keyword matches, injects domain context on first
hit, returns a brief reminder on repeat hits, and stays silent on no-match.

Usage (Claude Code hook):
    python -m library_server.hooks.scripts.prompt_scan

Stdin JSON fields:
    session_id   -- opaque session identifier
    prompt       -- the user's prompt text
    domains_dir  -- path to vault/domains/ directory
    dedup_dir    -- path to dedup state directory (typically /tmp or sessions dir)
    journal_path -- path to the routing JSONL journal

Stdout JSON (on match):
    {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": <str>}}

Stdout (no match):
    <empty>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from library_server.hooks.dedup import get_dedup_path, is_domain_injected, mark_domain_injected
from library_server.hooks.domain_scanner import load_domain_manifests, scan_prompt
from library_server.hooks.learning import log_routing_decision

# Token estimate for repeat-hit reminder messages
_REPEAT_TOKENS = 50


def process_prompt(
    prompt: str,
    session_id: str,
    domains_dir: Path,
    dedup_dir: Path,
    journal_path: Path,
) -> dict | None:
    """Scan prompt for domain matches and return injection payload or None.

    Parameters
    ----------
    prompt:
        The user's prompt text.
    session_id:
        Unique identifier for the current Claude Code session.
    domains_dir:
        Directory containing domain ``*.md`` manifest files.
    dedup_dir:
        Directory used to store per-session dedup state files.
    journal_path:
        Path to the JSONL routing journal.

    Returns
    -------
    dict | None
        On first hit: ``{"context": ..., "tokens": ..., "domain": ..., "match_type": "first_hit"}``
        On repeat hit: ``{"context": "Reminder: ...", "tokens": 50, "domain": ..., "match_type": "repeat"}``
        On no match: ``None``
    """
    manifests = load_domain_manifests(domains_dir)
    matches = scan_prompt(prompt, manifests)

    if not matches:
        log_routing_decision(
            journal_path=journal_path,
            session_id=session_id,
            prompt_keywords=[],
            matched_domain=None,
            match_type="no_match",
            injection_tokens=0,
        )
        return None

    # Use the first (highest priority) match
    match = matches[0]
    domain = match.domain
    dedup_path = dedup_dir / f"library-session-{session_id}.domains"

    if is_domain_injected(dedup_path, domain):
        # Repeat hit — return a lightweight reminder
        log_routing_decision(
            journal_path=journal_path,
            session_id=session_id,
            prompt_keywords=match.matched_keywords,
            matched_domain=domain,
            match_type="repeat",
            injection_tokens=_REPEAT_TOKENS,
        )
        return {
            "context": f"Reminder: {domain} context was loaded earlier this session.",
            "tokens": _REPEAT_TOKENS,
            "domain": domain,
            "match_type": "repeat",
        }

    # First hit — inject full domain content and mark as injected
    mark_domain_injected(dedup_path, domain)
    log_routing_decision(
        journal_path=journal_path,
        session_id=session_id,
        prompt_keywords=match.matched_keywords,
        matched_domain=domain,
        match_type="first_hit",
        injection_tokens=match.token_estimate,
    )
    return {
        "context": match.content,
        "tokens": match.token_estimate,
        "domain": domain,
        "match_type": "first_hit",
    }


def main() -> None:
    """Entry point: read JSON from stdin, write JSON to stdout or stay silent."""
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}

    prompt = data.get("prompt", "")
    session_id = data.get("session_id", "unknown")
    domains_dir = Path(data["domains_dir"]) if "domains_dir" in data else Path(".")
    dedup_dir = Path(data.get("dedup_dir", "/tmp"))
    journal_path = Path(data["journal_path"]) if "journal_path" in data else Path("/tmp/routing.jsonl")

    result = process_prompt(
        prompt=prompt,
        session_id=session_id,
        domains_dir=domains_dir,
        dedup_dir=dedup_dir,
        journal_path=journal_path,
    )

    if result is None:
        # Silent exit — no output
        return

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": result["context"],
        }
    }
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
