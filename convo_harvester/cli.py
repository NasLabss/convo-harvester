# -*- coding: utf-8 -*-
"""convo-harvester — generic collector of AI agent conversations.

Pulls the history of several tools (opencode, Antigravity, zcode, Claude
Code, Codex, Cursor, Cline...) and writes it as readable Markdown in a single
folder, incrementally. All texts are sanitized before writing
(secrets, tokens, and PII redacted — see convo_harvester.sanitize).

  python -m convo_harvester            # harvest all enabled tools (config.json)
  python -m convo_harvester --list     # list the available adapters
  python -m convo_harvester --tool opencode
  python -m convo_harvester --full     # ignore incremental, re-extract everything
  python -m convo_harvester --dry-run  # writes nothing, just shows what would be done
  python -m convo_harvester --output D:\\dump --config ./config.json

No path is hard-coded: everything starts from Path.home() + multi-OS
auto-detection, and can be overridden via config.json. See AGENTS.md / README.md.
"""

import argparse
import sys
from pathlib import Path

from .adapters import ADAPTERS
from .config import load_config, resolve_output_dir
from .render import render_md, safe_filename

# UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


# --------------------------------------------------------------------------- #
#  Writing (incremental) — rendering sanitizes BEFORE writing
# --------------------------------------------------------------------------- #

def write_conversation(out_root, conv, full, dry):
    tool_dir = out_root / conv["tool"]
    out_path = tool_dir / (safe_filename(conv["id"]) + ".md")

    src_mtime = conv.get("source_mtime")
    if (not full) and out_path.exists() and src_mtime \
            and out_path.stat().st_mtime >= src_mtime:
        return "skipped"

    if dry:
        return "would-write"

    tool_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_md(conv), encoding="utf-8")
    return "written"


# --------------------------------------------------------------------------- #
#  Main loop
# --------------------------------------------------------------------------- #

def run(cfg, out_root, only_tool, full, dry):
    home = Path.home()
    totals = {"written": 0, "skipped": 0, "would-write": 0, "tools": 0}

    print(f"convo-harvester — output: {out_root}")
    print(f"detected home: {home}")
    print("security: sanitization enabled (secrets/tokens/PII redacted)")
    if dry:
        print("(dry-run: nothing will be written)")
    print("")

    for name, meta in ADAPTERS.items():
        if only_tool and name != only_tool:
            continue
        opts = cfg["tools"].get(name, {"enabled": True, "path": None})
        if not only_tool and not opts.get("enabled", False):
            continue

        try:
            path, convs, note = meta["fn"](home, opts.get("path"))
        except Exception as e:
            print(f"[{name}] ADAPTER ERROR: {e}")
            continue

        if path is None:
            print(f"[{name}] not found.")
            if note:
                print(f"        note: {note}")
            continue

        totals["tools"] += 1
        stats = {"written": 0, "skipped": 0, "would-write": 0}
        for conv in convs:
            try:
                r = write_conversation(out_root, conv, full, dry)
                stats[r] = stats.get(r, 0) + 1
                totals[r] = totals.get(r, 0) + 1
            except Exception as e:
                print(f"[{name}] WRITE ERROR {conv.get('id')}: {e}")

        line = (f"[{name}] detected: {path}\n"
                f"        -> {len(convs)} conversations | "
                f"{stats['written']} written, "
                f"{stats['would-write']} to write (dry), "
                f"{stats['skipped']} up to date")
        print(line)
        if note:
            print(f"        note: {note}")

    print("")
    print(f"Done. Tools processed: {totals['tools']} | "
          f"written: {totals['written']} | "
          f"to write (dry): {totals['would-write']} | "
          f"up to date: {totals['skipped']}")
    return totals


def cmd_list():
    print("Available adapters:\n")
    for name, meta in ADAPTERS.items():
        tag = "primary" if meta.get("primary") else "bonus  "
        print(f"  [{tag}] {name:12s} {meta['desc']}")
    print("\n'primary' = enabled by default. Adjustable in config.json.")


def main():
    ap = argparse.ArgumentParser(
        description="Generic collector of AI agent conversations.")
    ap.add_argument("--list", action="store_true",
                    help="list adapters and exit")
    ap.add_argument("--tool", metavar="NAME",
                    help="run only one adapter (ignores enabled)")
    ap.add_argument("--full", action="store_true",
                    help="re-extract everything (ignores incremental)")
    ap.add_argument("--dry-run", action="store_true",
                    help="write nothing, show the plan")
    ap.add_argument("--output", metavar="DIR", help="output directory")
    ap.add_argument("--config", metavar="PATH", help="path to config.json")
    args = ap.parse_args()

    if args.list:
        cmd_list()
        return 0

    if args.tool and args.tool not in ADAPTERS:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {', '.join(ADAPTERS)}")
        return 2

    cfg, used = load_config(args.config)
    if used:
        print(f"config: {used}")
    else:
        print("config: (built-in defaults — no config.json found)")

    out_root = resolve_output_dir(cfg, args.output)
    run(cfg, out_root, args.tool, args.full, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
