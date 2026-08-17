# -*- coding: utf-8 -*-
"""
convo_harvester.adapters — per-tool extractors for convo-harvester.

Each adapter is a function `adapt_<tool>(home, override)` that:
  - automatically detects the tool's storage location
    (or uses `override` if provided in config.json),
  - returns a tuple `(detected_path, conversations, note)` where
    `conversations` is a list of NORMALIZED dicts:

    {
      "tool":        str,           # tool name
      "id":          str,           # unique identifier (used as the file name)
      "title":       str,           # readable title
      "project":     str,           # working folder / project (optional)
      "created":     int|str|None,  # creation date (epoch s/ms or ISO)
      "source_path": str,           # provenance (1 file or 1 folder)
      "source_mtime":float,         # max mtime of the read files -> incremental
      "messages":   [ {"role": str, "text": str, "ts": int|str|None}, ... ],
    }

TO ADD A TOOL (done by the user's agent):
  1. write an adapt_<tool>(home, override) function returning this format,
  2. register it in the ADAPTERS dict at the bottom of this file.
  Nothing else to touch: the engine (cli.py) handles the rest.

The detection/extraction logic is identical to the monolithic version
(original harvester.py/adapters.py): only the module split and the
sanitization (applied at render time, see render.py) changed.
"""

import os
import json
import sqlite3
from pathlib import Path


# --------------------------------------------------------------------------- #
#  Generic helpers (reusable by all adapters)
# --------------------------------------------------------------------------- #

def read_json(path):
    """Loads a JSON file, returns None on error."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def parse_json(text):
    """Parses a JSON string (1 JSONL line), returns None if invalid."""
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def read_lines(path):
    """Line-by-line iterator tolerant of encoding issues."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                yield line
    except Exception:
        return


def first_existing(candidates):
    """Returns the first existing path from a list of candidates, otherwise None."""
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return None


def appdata_roaming(home):
    return Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))


def appdata_local(home):
    return Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))


def xdg_data(home):
    return Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share"))


def mac_support(home):
    return home / "Library" / "Application Support"


def _block_text(content):
    """Extracts text from a 'content' that may be str, a list of blocks, or a dict."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                t = b.get("text") or b.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    if isinstance(content, dict):
        t = content.get("text") or content.get("content") or ""
        return t if isinstance(t, str) else ""
    return ""


def extract_generic_messages(data):
    """
    Generic heuristic: finds a message list in a JSON of unknown shape.
    Used by the zcode adapter (best-effort).
    """
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for key in ("messages", "history", "conversation", "turns",
                    "items", "events", "log", "chat"):
            if isinstance(data.get(key), list):
                arr = data[key]
                break
    if not arr:
        return []
    msgs = []
    for m in arr:
        if isinstance(m, str):
            if m.strip():
                msgs.append({"role": "?", "text": m, "ts": None})
            continue
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or m.get("type") or m.get("sender")
                or m.get("author") or "?")
        raw = m.get("content")
        if raw is None:
            raw = m.get("text", m.get("message", ""))
        text = _block_text(raw).strip()
        if not text:
            continue
        ts = (m.get("ts") or m.get("time") or m.get("timestamp")
              or m.get("created_at") or m.get("createdAt"))
        msgs.append({"role": str(role), "text": text, "ts": ts})
    return msgs


# --------------------------------------------------------------------------- #
#  opencode (sst)  —  ~/.local/share/opencode/storage
#  Format: session/<proj>/ses_*.json  ->  message/<sesid>/msg_*.json
#          ->  part/<msgid>/prt_*.json (type "text" = real content)
# --------------------------------------------------------------------------- #

def _opencode_candidates(home):
    return [
        xdg_data(home) / "opencode" / "storage",
        home / ".local" / "share" / "opencode" / "storage",
        mac_support(home) / "opencode" / "storage",
        appdata_local(home) / "opencode" / "storage",
    ]


def adapt_opencode(home, override):
    base = Path(override) if override else first_existing(_opencode_candidates(home))
    if not base or not base.exists():
        return None, [], None

    sess_dir = base / "session"
    msg_root = base / "message"
    part_root = base / "part"

    sessions = {}
    if sess_dir.is_dir():
        for sf in sess_dir.rglob("ses_*.json"):
            d = read_json(sf)
            if not d:
                continue
            sid = d.get("id", sf.stem)
            t = d.get("time") or {}
            sessions[sid] = {
                "title": d.get("title") or "Untitled",
                "project": d.get("directory", ""),
                "created": t.get("created"),
                "mtime": sf.stat().st_mtime,
            }

    convs = []
    # We iterate over the message folders (source of truth) and enrich
    # with session metadata when it exists: this also captures
    # "orphan" sessions without a session/*.json file.
    if not msg_root.is_dir():
        return str(base), convs, None
    for mdir in sorted(msg_root.iterdir()):
        if not mdir.is_dir() or not mdir.name.startswith("ses_"):
            continue
        sid = mdir.name
        meta = sessions.get(sid, {"title": "Untitled", "project": "",
                                  "created": None, "mtime": 0.0})
        mtime = meta.get("mtime") or 0.0

        loaded = []
        for mf in mdir.glob("msg_*.json"):
            md = read_json(mf)
            if not md:
                continue
            mtime = max(mtime, mf.stat().st_mtime)
            loaded.append(md)
        loaded.sort(key=lambda m: (m.get("time") or {}).get("created") or 0)

        msgs = []
        for md in loaded:
            msgid = md.get("id")
            if not msgid:
                continue
            pdir = part_root / msgid
            texts = []
            if pdir.is_dir():
                for pf in sorted(pdir.glob("prt_*.json"), key=lambda p: p.name):
                    pd = read_json(pf)
                    if not pd:
                        continue
                    mtime = max(mtime, pf.stat().st_mtime)
                    if pd.get("type") == "text" and (pd.get("text") or "").strip():
                        texts.append(pd["text"])
            text = "\n\n".join(texts).strip()
            if not text:
                continue
            msgs.append({
                "role": md.get("role", "?"),
                "text": text,
                "ts": (md.get("time") or {}).get("created"),
            })

        if not msgs:
            continue
        convs.append({
            "tool": "opencode", "id": sid, "title": meta["title"],
            "project": meta["project"], "created": meta["created"],
            "source_path": str(base), "source_mtime": mtime, "messages": msgs,
        })
    return str(base), convs, None


# --------------------------------------------------------------------------- #
#  Antigravity (Google)  —  ~/.gemini/antigravity/brain/<id>/.system_generated/logs/transcript.jsonl
# --------------------------------------------------------------------------- #

def adapt_antigravity(home, override):
    base = (Path(override) if override
            else first_existing([home / ".gemini" / "antigravity",
                                 home / ".antigravity"]))
    if not base or not base.exists():
        return None, [], None

    brain = base / "brain"
    convs = []
    if brain.is_dir():
        for folder in brain.iterdir():
            if not folder.is_dir():
                continue
            tp = folder / ".system_generated" / "logs" / "transcript.jsonl"
            if not tp.exists():
                continue
            msgs = []
            created = None
            for line in read_lines(tp):
                step = parse_json(line)
                if not step:
                    continue
                stype = step.get("type")
                source = step.get("source")
                content = step.get("content", "")
                cat = step.get("created_at", "")
                if created is None and cat:
                    created = cat
                if stype == "USER_INPUT":
                    clean = content
                    if "<USER_REQUEST>" in content:
                        clean = content.split("<USER_REQUEST>")[1] \
                                       .split("</USER_REQUEST>")[0].strip()
                    if clean.strip():
                        msgs.append({"role": "user", "text": clean, "ts": cat})
                elif stype == "PLANNER_RESPONSE" or source == "MODEL":
                    if content and content.strip():
                        msgs.append({"role": "assistant", "text": content, "ts": cat})
            if not msgs:
                continue
            convs.append({
                "tool": "antigravity", "id": folder.name, "title": folder.name,
                "project": "", "created": created, "source_path": str(tp),
                "source_mtime": tp.stat().st_mtime, "messages": msgs,
            })
    return str(base), convs, None


# --------------------------------------------------------------------------- #
#  zcode (z.ai)  —  BEST-EFFORT, format not confirmed on a real machine.
#  Known candidates (z.ai CLI docs): ~/.zai/sessions/*.json + ~/.zai/history.json
#  >>> The user's agent MUST confirm the real path/format. <<<
#  See AGENTS.md > "zcode" section.
# --------------------------------------------------------------------------- #

_ZCODE_NOTE = (
    "zcode best-effort: z.ai format not verified on a real machine. "
    "If 0 conversations OR raw dumps -> confirm the real path/format "
    "(see AGENTS.md > zcode) then set tools.zcode.path in config.json."
)


def _zcode_candidates(home):
    return [
        home / ".zai" / "sessions",
        home / ".zcode" / "sessions",
        home / ".z-ai" / "sessions",
        home / ".zai",            # fallback: sessions at the root
        appdata_roaming(home) / "zcode" / "sessions",
        mac_support(home) / "ZCode" / "sessions",
    ]


def adapt_zcode(home, override):
    base = Path(override) if override else first_existing(_zcode_candidates(home))
    if not base or not base.exists():
        return None, [], _ZCODE_NOTE

    convs = []
    json_files = sorted(base.glob("*.json"))
    # skip known flat config/history files
    json_files = [p for p in json_files if p.name.lower() != "history.json"]

    for sf in json_files:
        d = read_json(sf)
        if d is None:
            continue
        msgs = extract_generic_messages(d)
        mtime = sf.stat().st_mtime
        if msgs:
            title = sf.stem
            created = None
            if isinstance(d, dict):
                title = d.get("title") or d.get("name") or sf.stem
                created = d.get("created") or d.get("created_at") or d.get("createdAt")
            convs.append({
                "tool": "zcode", "id": sf.stem, "title": title, "project": "",
                "created": created, "source_path": str(sf),
                "source_mtime": mtime, "messages": msgs,
            })
        else:
            # unrecognized format -> raw dump (truncated) so nothing is lost
            raw = json.dumps(d, ensure_ascii=False, indent=2)[:20000]
            convs.append({
                "tool": "zcode", "id": sf.stem, "title": sf.stem, "project": "",
                "created": None, "source_path": str(sf), "source_mtime": mtime,
                "messages": [{
                    "role": "raw",
                    "text": "> Unknown zcode format — raw dump:\n\n```json\n"
                            + raw + "\n```",
                    "ts": None,
                }],
            })
    return str(base), convs, _ZCODE_NOTE


# --------------------------------------------------------------------------- #
#  Claude Code  —  ~/.claude/projects/<proj>/<session>.jsonl  (bonus)
# --------------------------------------------------------------------------- #

def _claude_text(message):
    return _block_text(message.get("content", "")) if isinstance(message, dict) else ""


def adapt_claudecode(home, override):
    base = (Path(override) if override
            else first_existing([home / ".claude" / "projects"]))
    if not base or not base.exists():
        return None, [], None

    convs = []
    for proj in base.iterdir():
        if not proj.is_dir():
            continue
        for jf in proj.glob("*.jsonl"):
            msgs = []
            for line in read_lines(jf):
                e = parse_json(line)
                if not e or e.get("type") not in ("user", "assistant"):
                    continue
                txt = _claude_text(e.get("message", {}))
                if not txt.strip():
                    continue
                msgs.append({
                    "role": "user" if e["type"] == "user" else "assistant",
                    "text": txt, "ts": e.get("timestamp"),
                })
            if not msgs:
                continue
            convs.append({
                "tool": "claudecode", "id": f"{proj.name}__{jf.stem}",
                "title": jf.stem, "project": proj.name, "created": None,
                "source_path": str(jf), "source_mtime": jf.stat().st_mtime,
                "messages": msgs,
            })
    return str(base), convs, None


# --------------------------------------------------------------------------- #
#  Codex (OpenAI)  —  ~/.codex/history.jsonl (+ session_index.jsonl)  (bonus)
# --------------------------------------------------------------------------- #

def adapt_codex(home, override):
    base = Path(override) if override else first_existing([home / ".codex"])
    if not base or not base.exists():
        return None, [], None
    hist = base / "history.jsonl"
    if not hist.exists():
        return str(base), [], None

    names = {}
    idx = base / "session_index.jsonl"
    if idx.exists():
        for line in read_lines(idx):
            it = parse_json(line)
            if it:
                names[it.get("id")] = it.get("thread_name")

    groups = {}
    order = []
    for line in read_lines(hist):
        e = parse_json(line)
        if not e:
            continue
        sid = e.get("session_id", "unknown")
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append(e)

    mtime = hist.stat().st_mtime
    convs = []
    for sid in order:
        entries = groups[sid]
        msgs = [{"role": "entry", "text": e.get("text", ""), "ts": e.get("ts")}
                for e in entries if (e.get("text") or "").strip()]
        if not msgs:
            continue
        convs.append({
            "tool": "codex", "id": str(sid),
            "title": names.get(sid) or "Session", "project": "",
            "created": entries[0].get("ts"), "source_path": str(hist),
            "source_mtime": mtime, "messages": msgs,
        })
    return str(base), convs, None


# --------------------------------------------------------------------------- #
#  Cursor (Composer moderne)  —  globalStorage/state.vscdb (table cursorDiskKV)  (bonus)
# --------------------------------------------------------------------------- #

def _cursor_candidates(home):
    return [
        appdata_roaming(home) / "Cursor" / "User" / "globalStorage" / "state.vscdb",
        mac_support(home) / "Cursor" / "User" / "globalStorage" / "state.vscdb",
        home / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
    ]


def adapt_cursor(home, override):
    db = Path(override) if override else first_existing(_cursor_candidates(home))
    if not db or not db.exists():
        return None, [], None

    convs = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = conn.cursor()

        titles = {}
        try:
            cur.execute("SELECT key, value FROM cursorDiskKV "
                        "WHERE key LIKE 'composerData:%'")
            for k, v in cur.fetchall():
                cid = k.split(":", 1)[-1]
                if isinstance(v, bytes):
                    v = v.decode("utf-8", "ignore")
                dd = parse_json(v)
                if dd:
                    titles[cid] = dd.get("name") or "Untitled"
        except Exception:
            pass

        bubbles = {}
        try:
            cur.execute("SELECT key, value FROM cursorDiskKV "
                        "WHERE key LIKE 'bubbleId:%' ORDER BY rowid")
            for k, v in cur.fetchall():
                parts = k.split(":")
                if len(parts) < 3:
                    continue
                cid = parts[1]
                if isinstance(v, bytes):
                    v = v.decode("utf-8", "ignore")
                b = parse_json(v)
                if not b:
                    continue
                text = b.get("text", "")
                if not text or not text.strip():
                    continue
                role = "user" if b.get("type") == 1 else "assistant"
                bubbles.setdefault(cid, []).append(
                    {"role": role, "text": text, "ts": None})
        except Exception:
            pass
        conn.close()
    except Exception as e:
        return str(db), [], f"cursor: SQLite error ({e})"

    mtime = db.stat().st_mtime
    for cid, msgs in bubbles.items():
        if not msgs:
            continue
        convs.append({
            "tool": "cursor", "id": cid, "title": titles.get(cid, "Untitled"),
            "project": "", "created": None, "source_path": str(db),
            "source_mtime": mtime, "messages": msgs,
        })
    return str(db), convs, None


# --------------------------------------------------------------------------- #
#  Cline / Claude-Dev (VS Code)  —  globalStorage/.../tasks/<id>/ui_messages.json  (bonus)
# --------------------------------------------------------------------------- #

def _cline_candidates(home):
    leaf = Path("Code") / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "tasks"
    return [
        appdata_roaming(home) / leaf,
        mac_support(home) / leaf,
        home / ".config" / leaf,
    ]


def adapt_cline(home, override):
    base = Path(override) if override else first_existing(_cline_candidates(home))
    if not base or not base.exists():
        return None, [], None

    convs = []
    for folder in base.iterdir():
        if not folder.is_dir():
            continue
        uf = folder / "ui_messages.json"
        if not uf.exists():
            continue
        data = read_json(uf)
        if not isinstance(data, list):
            continue
        msgs = []
        for m in data:
            if not isinstance(m, dict):
                continue
            text = m.get("text", "")
            if not text or not text.strip():
                continue
            msgs.append({"role": m.get("type", "?"), "text": text, "ts": m.get("ts")})
        if not msgs:
            continue
        convs.append({
            "tool": "cline", "id": folder.name, "title": f"task_{folder.name}",
            "project": "", "created": None, "source_path": str(uf),
            "source_mtime": uf.stat().st_mtime, "messages": msgs,
        })
    return str(base), convs, None


# --------------------------------------------------------------------------- #
#  REGISTRY — the only thing to edit to plug/unplug a tool.
#  "primary": True = the user's target tool (enabled by default).
# --------------------------------------------------------------------------- #

ADAPTERS = {
    "opencode":    {"fn": adapt_opencode,    "primary": True,
                    "desc": "opencode (sst) — ~/.local/share/opencode/storage"},
    "antigravity": {"fn": adapt_antigravity, "primary": True,
                    "desc": "Antigravity (Google) — ~/.gemini/antigravity/brain"},
    "zcode":       {"fn": adapt_zcode,       "primary": True,
                    "desc": "zcode (z.ai) — ~/.zai/sessions (best-effort, to be confirmed)"},
    "claudecode":  {"fn": adapt_claudecode,  "primary": False,
                    "desc": "Claude Code — ~/.claude/projects/*/*.jsonl"},
    "codex":       {"fn": adapt_codex,       "primary": False,
                    "desc": "Codex (OpenAI) — ~/.codex/history.jsonl"},
    "cursor":      {"fn": adapt_cursor,      "primary": False,
                    "desc": "Cursor — globalStorage/state.vscdb (cursorDiskKV)"},
    "cline":       {"fn": adapt_cline,       "primary": False,
                    "desc": "Cline/Claude-Dev — globalStorage/.../tasks"},
}
