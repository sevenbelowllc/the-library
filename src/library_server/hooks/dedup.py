"""Hook infrastructure: session deduplication for domain injection.

Tracks which domain context files have already been injected into the
current Claude Code session, so they are not re-injected on every prompt.
Each session gets a lightweight flat file in ``/tmp/``.
"""

from __future__ import annotations

from pathlib import Path


def get_dedup_path(session_id: str) -> Path:
    """Return the dedup file path for *session_id*.

    The file lives at ``/tmp/library-session-{session_id}.domains``.

    Parameters
    ----------
    session_id:
        Opaque string that uniquely identifies the current Claude Code session.

    Returns
    -------
    Path
        Absolute path to the dedup file (may not exist yet).
    """
    return Path(f"/tmp/library-session-{session_id}.domains")


def is_domain_injected(dedup_path: Path, domain: str) -> bool:
    """Return ``True`` if *domain* has been recorded in *dedup_path*.

    Performs an exact line-level match (stripped); a domain that is a
    *substring* of another entry is **not** considered a match.

    Parameters
    ----------
    dedup_path:
        Path returned by :func:`get_dedup_path`.
    domain:
        Domain name to check (e.g. ``"auth"``).

    Returns
    -------
    bool
    """
    if not dedup_path.is_file():
        return False
    for line in dedup_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == domain:
            return True
    return False


def mark_domain_injected(dedup_path: Path, domain: str) -> None:
    """Append *domain* to *dedup_path*, creating the file if necessary.

    Idempotent: if *domain* is already present the file is left unchanged.

    Parameters
    ----------
    dedup_path:
        Path returned by :func:`get_dedup_path`.
    domain:
        Domain name to record (e.g. ``"auth"``).
    """
    if is_domain_injected(dedup_path, domain):
        return
    with open(dedup_path, "a", encoding="utf-8") as fh:
        fh.write(domain + "\n")
