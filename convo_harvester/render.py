# -*- coding: utf-8 -*-
"""Markdown rendering of conversations, with systematic sanitization.

The sanitization application point is HERE: render_md() passes every
text (messages, title, project) through redact_text() BEFORE it is written
to disk. Every .md write goes through render_md() — it is therefore
impossible to persist a detected secret, including in the raw dumps
of the zcode adapter.
"""

import re
from datetime import datetime

from .sanitize import redact_text

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name, maxlen=120):
    name = _ILLEGAL.sub("_", str(name)).strip().strip(".")
    return (name or "no_id")[:maxlen]


def to_iso(value):
    """Normalizes a date (epoch s, epoch ms, or already ISO) into a readable string."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    try:
        v = float(value)
        if v > 1e12:        # milliseconds
            v /= 1000.0
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def render_md(conv):
    out = []
    out.append(f"# {redact_text(conv.get('title') or conv.get('id'))}")
    out.append("")
    out.append(f"- **Tool** : {conv['tool']}")
    out.append(f"- **ID** : {conv['id']}")
    if conv.get("project"):
        out.append(f"- **Project** : {redact_text(conv['project'])}")
    if conv.get("created") not in (None, ""):
        out.append(f"- **Created** : {to_iso(conv['created'])}")
    out.append(f"- **Messages** : {len(conv['messages'])}")
    out.append(f"- **Source** : {conv.get('source_path', '')}")
    out.append("")
    out.append("---")
    out.append("")
    for m in conv["messages"]:
        role = (m.get("role") or "?").upper()
        ts = to_iso(m.get("ts"))
        head = f"**[{role}]**" + (f" ({ts})" if ts else "")
        out.append(head)
        out.append("")
        out.append(redact_text(m.get("text") or "").rstrip())
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)
