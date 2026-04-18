"""Configuration loading and validation."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_FILENAME = "library-config.yaml"


@dataclass
class LibraryConfig:
    """Parsed library configuration."""

    raw: dict[str, Any] = field(default_factory=dict)
    path: Path = field(default_factory=lambda: Path.cwd() / CONFIG_FILENAME)

    def get_section(self, section: str) -> dict:
        return self.raw.get(section, {})

    def set_value(self, section: str, key: str, value: Any) -> None:
        if section not in self.raw:
            self.raw[section] = {}
        self.raw[section][key] = value

    def to_dict(self) -> dict:
        return dict(self.raw)

    def save(self) -> None:
        with open(self.path, "w") as f:
            yaml.dump(self.raw, f, default_flow_style=False, sort_keys=False)


def resolve_checkpoint_dir(config: LibraryConfig) -> Path:
    """Resolve the checkpoint directory, enforcing the Reading Room boundary.

    Hard rule: checkpoints MUST live under reading_room.path. The directory is
    auto-created. If checkpoints.path is set, it is validated to resolve under
    reading_room.path; otherwise, it defaults to <reading_room.path>/checkpoints.

    Raises:
        ValueError: if reading_room.path is not configured, or if an explicit
        checkpoints.path resolves outside the Reading Room.
    """
    reading_room = config.get_section("reading_room").get("path")
    if not reading_room:
        raise ValueError(
            "reading_room.path is not configured. The Library requires a Reading "
            "Room before checkpoints can be written. Set reading_room.path in "
            "library-config.yaml."
        )

    config_dir = config.path.parent if config.path else Path.cwd()
    rr_path = (config_dir / reading_room).resolve() if not Path(reading_room).is_absolute() else Path(reading_room).resolve()

    explicit = config.get_section("checkpoints").get("path")
    if explicit:
        cp_path = (config_dir / explicit).resolve() if not Path(explicit).is_absolute() else Path(explicit).resolve()
        if not (cp_path == rr_path or rr_path in cp_path.parents):
            raise ValueError(
                f"checkpoints.path ({cp_path}) must live under reading_room.path "
                f"({rr_path}). The Library enforces this so all session artifacts "
                f"stay co-located with the Reading Room."
            )
    else:
        cp_path = rr_path / "checkpoints"

    cp_path.mkdir(parents=True, exist_ok=True)
    return cp_path


_STANDARDS_REQUIRED_KEYS = ("name", "path", "applies_to")


def autodetect_jira_workflow(statuses_response: list[dict]) -> dict:
    """Given the JSON body of `GET /rest/api/3/project/{key}/statuses`, derive
    a pm.workflow block with a best-effort ordered state list and named keys.

    The Jira response is a list of issue types, each with a "statuses" array
    of {id, name, ...}. We collect unique status names in the order they first
    appear and map well-known synonyms to the named keys.

    Raises:
        ValueError: if no statuses can be derived. Silent fallback would hide
        a misconfigured Jira project.
    """
    states: list[str] = []
    seen: set[str] = set()
    for issue_type in statuses_response or []:
        for status in issue_type.get("statuses", []) or []:
            name = status.get("name")
            if name and name not in seen:
                seen.add(name)
                states.append(name)
    if not states:
        raise ValueError("No statuses returned from Jira; cannot autodetect workflow.")

    def _match(candidates: tuple[str, ...]) -> str | None:
        for s in states:
            low = s.lower()
            if any(c in low for c in candidates):
                return s
        return None

    return {
        "states": states,
        "in_progress": _match(("in progress", "doing", "wip")) or states[min(1, len(states) - 1)],
        "in_review": _match(("review", "qa", "test")) or states[min(2, len(states) - 1)],
        "closed": _match(("closed", "done", "resolved", "complete")) or states[-1],
    }


def resolve_standards(config: LibraryConfig, repo_name: str) -> list[dict]:
    """Resolve the standards block for a given repo name.

    Returns a list of dicts with keys: name, path (as declared, relative to the
    reading room), absolute_path (resolved Path), applies_to. Entries whose
    applies_to does not match repo_name or "*" are filtered out.

    Raises:
        ValueError: if reading_room.path is missing but a standards block exists,
        or if a standards entry is missing required keys. Silent-skip is a
        standards violation — malformed config must surface loudly.
    """
    raw = config.raw.get("standards")
    if not raw:
        return []

    reading_room = config.get_section("reading_room").get("path")
    if not reading_room:
        raise ValueError(
            "standards block requires reading_room.path to resolve paths against."
        )

    config_dir = config.path.parent if config.path else Path.cwd()
    rr_path = (
        Path(reading_room).resolve()
        if Path(reading_room).is_absolute()
        else (config_dir / reading_room).resolve()
    )

    out: list[dict] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"standards[{i}] must be a mapping, got {type(entry).__name__}")
        missing = [k for k in _STANDARDS_REQUIRED_KEYS if k not in entry]
        if missing:
            raise ValueError(
                f"standards[{i}] is missing required keys: {missing}. "
                f"Every entry must declare name, path, applies_to."
            )
        applies_to = entry["applies_to"]
        if not isinstance(applies_to, list) or not applies_to:
            raise ValueError(
                f"standards[{i}].applies_to must be a non-empty list "
                f"of repo names or [\"*\"]."
            )
        if "*" not in applies_to and repo_name not in applies_to:
            continue
        out.append(
            {
                "name": entry["name"],
                "path": entry["path"],
                "absolute_path": (rr_path / entry["path"]).resolve(),
                "applies_to": list(applies_to),
            }
        )
    return out


def load_config(config_path: Path | None = None) -> LibraryConfig:
    """Load config from yaml file. Returns empty config if file doesn't exist."""
    path = config_path or Path.cwd() / CONFIG_FILENAME
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    return LibraryConfig(raw=raw, path=path)


def validate_config(config: LibraryConfig) -> dict:
    """Validate a loaded config for completeness and dependency availability.

    Returns:
        {"valid": bool, "warnings": [str, ...]}
    """
    warnings: list[str] = []

    # Check required sections
    library = config.get_section("library")
    if not library.get("version"):
        warnings.append("Missing library.version — config may be malformed")

    # Check vault path exists if configured
    vault = config.get_section("vault")
    vault_path = vault.get("path")
    if vault_path and not Path(vault_path).exists():
        warnings.append(f"Vault path does not exist: {vault_path}")

    # Check Graphify availability if enabled
    graphify = config.get_section("graphify")
    if graphify.get("enabled"):
        if not shutil.which("graphify"):
            warnings.append(
                "Graphify is enabled but CLI not found. "
                "Install with: pip install the-library[graphify]"
            )

    # Check PM provider validity
    pm = config.get_section("pm")
    provider = pm.get("provider", "none")
    if provider not in ("jira", "linear", "none"):
        warnings.append(f"Unknown PM provider: {provider}. Use 'jira', 'linear', or 'none'.")

    # Check pm.workflow — named state keys must appear in states list
    workflow = pm.get("workflow") or {}
    if workflow:
        states = workflow.get("states") or []
        if not isinstance(states, list) or not all(isinstance(s, str) for s in states):
            warnings.append("pm.workflow.states must be a list of state-name strings")
        else:
            for key in ("in_progress", "in_review", "closed"):
                val = workflow.get(key)
                if val is None:
                    warnings.append(f"pm.workflow.{key} is not set — state transitions cannot be resolved")
                elif val not in states:
                    warnings.append(
                        f"pm.workflow.{key}={val!r} is not present in pm.workflow.states {states}"
                    )

    # Check memory path
    memory = config.get_section("memory")
    memory_path = memory.get("path")
    if memory_path and not Path(memory_path).exists():
        warnings.append(f"Memory path does not exist: {memory_path} (will be created on first use)")

    memory_cfg = config.raw.get("memory", {})
    if memory_cfg:
        budgets = memory_cfg.get("budgets", {})
        if budgets.get("critical", 300) + budgets.get("fresh", 500) > 1000:
            warnings.append("CRITICAL + FRESH budget exceeds 1000 tokens — high baseline cost")
        learning = memory_cfg.get("keyword_learning", {})
        if learning.get("hit_threshold", 0.8) <= learning.get("noise_threshold", 0.3):
            warnings.append("hit_threshold must be greater than noise_threshold")

    context_cfg = config.raw.get("context", {})
    if context_cfg:
        warn = context_cfg.get("warn_percentage", 50)
        checkpoint = context_cfg.get("checkpoint_percentage", 60)
        if warn >= checkpoint:
            warnings.append("warn_percentage must be less than checkpoint_percentage")

    # Check vault builder config
    vb = config.raw.get("vault_builder", {})
    if vb:
        vb_mode = vb.get("mode", "create")
        if vb_mode not in ("create", "enrich"):
            warnings.append(f"vault_builder.mode must be 'create' or 'enrich', got: {vb_mode}")
        if not vb.get("output_vault"):
            warnings.append("vault_builder.output_vault is not configured")

    return {"valid": len(warnings) == 0, "warnings": warnings}
