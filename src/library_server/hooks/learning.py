"""Auto-learning engine for the MMU routing journal.

Observes routing accuracy and proposes keyword improvements by maintaining
a JSONL journal of routing decisions and their outcomes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from library_server.types import RoutingOutcome


def log_routing_decision(
    journal_path: Path,
    session_id: str,
    prompt_keywords: list[str],
    matched_domain: str | None,
    match_type: str,
    injection_tokens: int,
) -> None:
    """Append a routing decision entry to the JSONL journal.

    Args:
        journal_path: Path to the JSONL journal file.
        session_id: Unique identifier for this session.
        prompt_keywords: Keywords extracted from the prompt.
        matched_domain: Domain that was matched (or None).
        match_type: How the match was made (e.g. "keyword", "exclude", "none").
        injection_tokens: Number of tokens injected for the matched domain.
    """
    joined = " ".join(prompt_keywords)
    prompt_hash = hashlib.sha256(joined.encode()).hexdigest()[:12]

    entry = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "session_id": session_id,
        "prompt_hash": prompt_hash,
        "prompt_keywords": prompt_keywords,
        "matched_domain": matched_domain,
        "match_type": match_type,
        "injection_tokens": injection_tokens,
        "outcome": None,
        "outcome_signal": "",
    }

    journal_path = Path(journal_path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    with journal_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def update_routing_outcome(
    journal_path: Path,
    session_id: str,
    outcome: RoutingOutcome,
    outcome_signal: str,
) -> None:
    """Update the last pending entry for session_id with an outcome.

    Finds the last entry for the given session_id where outcome is None,
    sets outcome and outcome_signal, then rewrites the file.

    Args:
        journal_path: Path to the JSONL journal file.
        session_id: Session whose last pending entry should be updated.
        outcome: The routing outcome to record.
        outcome_signal: Human-readable explanation of the outcome.
    """
    entries = read_journal(journal_path)
    if not entries:
        return

    # Find the last entry for this session_id with outcome == None
    last_idx = None
    for i in range(len(entries) - 1, -1, -1):
        if entries[i]["session_id"] == session_id and entries[i]["outcome"] is None:
            last_idx = i
            break

    if last_idx is None:
        return

    entries[last_idx]["outcome"] = outcome.value
    entries[last_idx]["outcome_signal"] = outcome_signal

    journal_path = Path(journal_path)
    with journal_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def read_journal(journal_path: Path) -> list[dict]:
    """Read all JSONL entries from the routing journal.

    Args:
        journal_path: Path to the JSONL journal file.

    Returns:
        List of entry dicts. Empty list if file missing or empty.
    """
    journal_path = Path(journal_path)
    if not journal_path.exists():
        return []

    entries = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def analyze_routing_accuracy(
    journal_path: Path,
    min_observations: int = 10,
) -> dict[str, dict]:
    """Analyze routing accuracy per domain from the journal.

    Groups entries by matched_domain and filters to domains with at least
    min_observations entries that have a resolved outcome.

    Args:
        journal_path: Path to the JSONL journal file.
        min_observations: Minimum number of resolved entries required per domain.

    Returns:
        Dict keyed by domain name, each value containing:
          - accuracy: float (hits / total)
          - hits: int
          - total: int
          - noise_count: int
          - misses_count: int
    """
    entries = read_journal(journal_path)

    # Group resolved entries by domain
    domain_entries: dict[str, list[dict]] = {}
    for entry in entries:
        if entry.get("outcome") is None:
            continue
        domain = entry.get("matched_domain") or "__none__"
        domain_entries.setdefault(domain, []).append(entry)

    report: dict[str, dict] = {}
    for domain, domain_list in domain_entries.items():
        if len(domain_list) < min_observations:
            continue

        hits = sum(
            1 for e in domain_list if e["outcome"] == RoutingOutcome.HIT.value
        )
        noise = sum(
            1 for e in domain_list if e["outcome"] == RoutingOutcome.NOISE.value
        )
        misses = sum(
            1 for e in domain_list if e["outcome"] == RoutingOutcome.MISS.value
        )
        total = len(domain_list)
        accuracy = hits / total if total > 0 else 0.0

        report[domain] = {
            "accuracy": accuracy,
            "hits": hits,
            "total": total,
            "noise_count": noise,
            "misses_count": misses,
        }

    return report


def detect_drift(
    journal_path: Path,
    window_entries: int = 30,
    drop_threshold: float = 0.4,
) -> list[dict]:
    """Detect domains whose recent routing accuracy has dropped significantly.

    For each domain, compares lifetime accuracy against the accuracy over the
    most recent window_entries. Flags domains where:
      - lifetime accuracy > 0.5
      - recent accuracy < drop_threshold

    Args:
        journal_path: Path to the JSONL journal file.
        window_entries: Number of recent entries per domain to use as the window.
        drop_threshold: Recent accuracy below this triggers a drift alert.

    Returns:
        List of drift dicts, each containing:
          - domain: str
          - lifetime_accuracy: float
          - recent_accuracy: float
          - window_size: int (actual entries in the window)
          - recommendation: str
    """
    entries = read_journal(journal_path)

    # Group resolved entries by domain, preserving insertion order
    domain_entries: dict[str, list[dict]] = {}
    for entry in entries:
        if entry.get("outcome") is None:
            continue
        domain = entry.get("matched_domain") or "__none__"
        domain_entries.setdefault(domain, []).append(entry)

    drift_report: list[dict] = []

    for domain, domain_list in domain_entries.items():
        total = len(domain_list)
        if total == 0:
            continue

        lifetime_hits = sum(
            1 for e in domain_list if e["outcome"] == RoutingOutcome.HIT.value
        )
        lifetime_accuracy = lifetime_hits / total

        if lifetime_accuracy <= 0.5:
            continue

        # Recent window
        window = domain_list[-window_entries:]
        window_size = len(window)
        recent_hits = sum(
            1 for e in window if e["outcome"] == RoutingOutcome.HIT.value
        )
        recent_accuracy = recent_hits / window_size if window_size > 0 else 0.0

        if recent_accuracy < drop_threshold:
            drift_report.append(
                {
                    "domain": domain,
                    "lifetime_accuracy": lifetime_accuracy,
                    "recent_accuracy": recent_accuracy,
                    "window_size": window_size,
                    "recommendation": (
                        f"Review keywords for domain '{domain}': "
                        f"lifetime accuracy {lifetime_accuracy:.0%} has dropped to "
                        f"{recent_accuracy:.0%} over the last {window_size} entries. "
                        "Consider pruning over-broad keywords or adding excludes."
                    ),
                }
            )

    return drift_report
