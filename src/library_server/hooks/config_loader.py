"""Hook infrastructure: config loader.

Loads library-config.yaml from a project directory and deep-merges it
with built-in defaults covering all MMU sections.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


DEFAULTS: dict[str, Any] = {
    "memory": {
        "session_dir": "~/.library/sessions",
        "budgets": {
            "critical": 300,
            "fresh": 500,
            "moderate_max": 1500,
            "domain_file_max": 500,
        },
        "pruning": {
            "graduation_threshold": 5,
            "hitl_required": True,
        },
        "keyword_learning": {
            "enabled": True,
            "hitl_required": True,
            "min_observations": 10,
            "hit_threshold": 0.8,
            "noise_threshold": 0.3,
            "drift_window_days": 30,
            "drift_drop_threshold": 0.4,
        },
    },
    "context": {
        "warn_percentage": 50,
        "checkpoint_percentage": 60,
    },
    "hooks": {
        "enabled": True,
        "session_start": True,
        "user_prompt_submit": True,
        "stop": True,
        "pre_compact": True,
        "session_end": True,
        "status_line": True,
    },
}


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overrides* into a copy of *defaults*.

    - Scalar override values replace default values.
    - Dict override values are merged recursively.
    - *defaults* is never mutated.
    """
    result = copy.deepcopy(defaults)
    for key, override_value in overrides.items():
        default_value = result.get(key)
        if isinstance(default_value, dict) and isinstance(override_value, dict):
            result[key] = _deep_merge(default_value, override_value)
        else:
            result[key] = copy.deepcopy(override_value)
    return result


def load_hook_config(project_dir: Path) -> dict[str, Any]:
    """Load ``library-config.yaml`` from *project_dir* and deep-merge with defaults.

    If the file does not exist, the built-in defaults are returned verbatim.
    Any keys present in the file override the corresponding defaults; keys
    absent in the file retain their default values.

    Parameters
    ----------
    project_dir:
        Directory that may contain a ``library-config.yaml`` file.

    Returns
    -------
    dict
        Configuration dict with all MMU sections populated.
    """
    config_path = project_dir / "library-config.yaml"
    overrides: dict[str, Any] = {}

    if config_path.is_file():
        with open(config_path) as fh:
            loaded = yaml.safe_load(fh)
        if isinstance(loaded, dict):
            overrides = loaded

    return _deep_merge(DEFAULTS, overrides)
