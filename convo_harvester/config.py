# -*- coding: utf-8 -*-
"""External configuration for convo-harvester (config.json).

Resolution order identical to the monolithic version:
  1. --config <path> if provided (CLI)
  2. config.json in the current directory, then at the project root
     (next to config.example.json)
  3. config.example.json at the project root
  4. built-in defaults

Missing keys are completed with the defaults. When the tool is run from
the project folder, config.json is therefore found in the same place
as in the monolithic version (next to the script).
"""

import json
from pathlib import Path

from .adapters import ADAPTERS

# Package directory (convo_harvester/) and project root (parent).
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def default_config():
    tools = {}
    for name, meta in ADAPTERS.items():
        tools[name] = {"enabled": bool(meta.get("primary")), "path": None}
    return {"output_dir": "harvest_output", "tools": tools}


def load_config(explicit_path):
    """
    Resolution order:
      1. --config <path> if provided
      2. config.json in the current directory, then next to the package
      3. config.example.json next to the package
      4. built-in defaults
    Missing keys are completed with the defaults.
    """
    cfg = default_config()
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    else:
        candidates.append(Path.cwd() / "config.json")
        candidates.append(PROJECT_ROOT / "config.json")
        candidates.append(PROJECT_ROOT / "config.example.json")

    used = None
    loaded = {}
    for c in candidates:
        if c and c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                used = c
                break
            except Exception as e:
                print(f"[!] unreadable config {c}: {e}")
                loaded = {}
                break

    if loaded:
        if "output_dir" in loaded:
            cfg["output_dir"] = loaded["output_dir"]
        for name, opts in (loaded.get("tools") or {}).items():
            if name not in cfg["tools"]:
                cfg["tools"][name] = {"enabled": True, "path": None}
            if isinstance(opts, dict):
                cfg["tools"][name].update(opts)
    return cfg, used


def resolve_output_dir(cfg, cli_output):
    """Output folder: --output > config.json > default. Relative -> cwd."""
    raw = cli_output or cfg.get("output_dir") or "harvest_output"
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p
