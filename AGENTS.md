# AGENTS.md — guide for the agent installing convo-harvester

You are the AI agent in charge of setting up **convo-harvester** on your
user's machine. This folder is self-contained and generic: your job is to
adapt it to THIS machine, verify it with real evidence, then automate it.

Assume nothing: **detect, run, verify**. Do not declare "installed"
without having seen real `.md` files produced.

---

## What the system does

`convo_harvester/` is a Python package (stdlib only) that reads the history of
several AI tools and writes it as Markdown into `output_dir`, one file per
conversation, incrementally. The 7 adapters live in
`convo_harvester/adapters.py` (the `ADAPTERS` registry). `install_scheduler.py`
schedules the daily run.

**Security:** all content is passed through `redact_text()` (module
`convo_harvester/sanitize.py`) at Markdown render time, BEFORE writing.
Secrets, tokens and PII are replaced with `[REDACTED]` — nothing sensitive
can be persisted.

Priority target tools: **opencode, antigravity, zcode**. Bonus tools shipped but
disabled: claudecode, codex, cursor, cline.

---

## Installation procedure (do it in order)

### 1. Check Python
```bash
python --version        # >= 3.8 required, standard library only
```

### 2. Discover what the machine contains
```bash
python -m convo_harvester --list
python -m convo_harvester --dry-run
```
The `--dry-run` shows, for each tool: `detected: <path>` + number of
conversations, or `not found`. That is your starting map.

### 3. Create the config
```bash
cp config.example.json config.json     # copy ... on Windows
```
Enable only the tools actually present (seen in step 2). Also enable
the bonus tools (claudecode, codex, cursor, cline) if the user uses them.

### 4. For each tool reported "not found" but expected to exist: find the real path
Auto-detection covers the standard locations. If a tool the user
uses shows up as "not found", locate its data folder and fill in
`tools.<tool>.path` in `config.json`. Search leads:
- Windows: `%APPDATA%`, `%LOCALAPPDATA%`, `~/.local/share`, `~/.<tool>`
- macOS: `~/Library/Application Support/<tool>`, `~/.<tool>`
- Linux: `~/.local/share/<tool>`, `~/.config/<tool>`, `~/.<tool>`

### 5. Run for real and VERIFY (mandatory)
```bash
python -m convo_harvester
```
Then actually open 1 or 2 produced files in `harvest_output/<tool>/`
and confirm the content (roles + text) is correct and that any secret
is properly `[REDACTED]`. Count the files.
Do not rely on the exit code alone.

### 6. Automate
```bash
python install_scheduler.py            # see the plan first
python install_scheduler.py --install  # then install (daily)
```
On Windows, `schtasks` may require administrator rights — warn the
user if installation fails for that reason.

---

## ⚠️ zcode (z.ai) — absolutely must be confirmed

The `zcode` adapter is **best-effort**: its format could not be verified
on a real installation. It tries `~/.zai/sessions/*.json` (and variants) and
parses messages generically (`messages` / `history` / `conversation`…).

**Your mission on zcode:**
1. Find where zcode/z.ai actually stores history on THIS machine.
   Candidates: `~/.zai/sessions`, `~/.zai/history.json`, `~/.zcode/`, or the
   ZCode desktop app data folder (`%APPDATA%` / `Application Support`).
2. Open one of those files and look at its real JSON structure.
3. If the structure differs (different message key, block content, etc.):
   - simple case → adjust `extract_generic_messages()` in `adapters.py`;
   - specific case → rewrite `adapt_zcode()` for that exact structure.
4. Fill in `tools.zcode.path` if the path is not auto-detected.
5. Re-run `python -m convo_harvester --tool zcode --full` and verify the `.md` produced.

Symptom "to fix": 0 zcode conversations, OR files containing
"Unknown zcode format — raw dump". The raw dump is intentional: no
data is lost, but the proper parser must be written. (Note: even the
raw dump goes through sanitization before being written.)

---

## Adding a new tool

In `convo_harvester/adapters.py`:

```python
def adapt_mytool(home, override):
    base = Path(override) if override else first_existing([
        home / ".mytool" / "sessions",          # multi-OS candidates
        appdata_roaming(home) / "MyTool",
    ])
    if not base or not base.exists():
        return None, [], None

    convs = []
    for f in Path(base).glob("*.json"):
        data = read_json(f)
        msgs = extract_generic_messages(data)   # or your dedicated parsing
        if not msgs:
            continue
        convs.append({
            "tool": "mytool", "id": f.stem, "title": f.stem, "project": "",
            "created": None, "source_path": str(f),
            "source_mtime": f.stat().st_mtime, "messages": msgs,
        })
    return str(base), convs, None
```

Then register it in `ADAPTERS`:

```python
"mytool": {"fn": adapt_mytool, "primary": True,
           "desc": "MyTool — ~/.mytool/sessions"},
```

Expected normalized format of a conversation (respect it exactly):
```python
{
  "tool": str, "id": str, "title": str, "project": str,
  "created": int|str|None, "source_path": str, "source_mtime": float,
  "messages": [ {"role": str, "text": str, "ts": int|str|None}, ... ],
}
```
`source_mtime` must be the most recent mtime among the files read for
that conversation: it drives the incremental logic.

---

## Final checklist (tick before saying "done")
- [ ] `python -m convo_harvester --dry-run` detects the right tools
- [ ] `config.json` reflects the tools actually used
- [ ] zcode confirmed (real path + real format, no residual raw dump)
- [ ] `python -m convo_harvester` produced `.md` files, opened and manually verified
- [ ] no secret visible in the produced `.md` files (everything is `[REDACTED]`)
- [ ] auto-run installed (`install_scheduler.py --install`) and confirmed
