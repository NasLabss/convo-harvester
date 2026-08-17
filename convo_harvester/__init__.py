# -*- coding: utf-8 -*-
"""convo-harvester — collector of local AI agent conversations.

Pulls the history of 7 tools (opencode, Antigravity, zcode, Claude Code,
Codex, Cursor, Cline) and writes it as incremental Markdown, with automatic
redaction of secrets (tokens, private keys, passwords, PII) before any
writing. No external dependencies: standard library only. No data leaves
the machine.

Usage:
    python -m convo_harvester            # harvest enabled tools
    python -m convo_harvester --list     # list adapters
    python -m convo_harvester --dry-run  # plan without writing
"""

from .cli import main
from .config import load_config
from .sanitize import redact_text, redact_value

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "main",
    "load_config",
    "redact_text",
    "redact_value",
]
