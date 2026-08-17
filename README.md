# convo-harvester

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)]()
[![Platform: Multi-OS](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

**convo-harvester** is a lightweight, local-first CLI utility designed to collect, normalize, and incrementally archive conversation histories from local AI coding assistants and CLI agents into structured, searchable Markdown files.

It operates entirely offline with **zero external dependencies** (Python standard library only), automatically discovering local agent data stores across Windows, macOS, and Linux.

---

## 🛡️ Security & Privacy Architecture

AI agent logs frequently contain runtime credentials: API keys, database connection strings, JWT tokens, and PII. 

**convo-harvester enforces deterministic secret scrubbing at render time.** No raw secret is ever written to disk.

### Redaction Matrix

All matching secrets are automatically sanitized and replaced with `[REDACTED]`:

| Category | Targeted Signatures & Formats |
|---|---|
| **Cryptographic Keys** | PEM/PKCS8 private key blocks (`-----BEGIN ... PRIVATE KEY-----`) |
| **Provider API Keys** | OpenAI (`sk-...`), Anthropic (`sk-ant-...`), Hugging Face (`hf_...`), GitHub (`ghp_...`, `gho_...`, `github_pat_...`), AWS (`AKIA...`), Google (`AIza...`), Stripe (`sk_live_...`, `rk_live_...`), NPM (`npm_...`), Slack (`xoxb-...`) |
| **Structured Tokens** | JWT payloads (`eyJ...`), Bearer authorization headers, Telegram bot tokens, Discord webhook endpoints |
| **Labeled Secrets** | Key-value pairs matching `api_key`, `client_secret`, `password`, `token`, `database_url` across JSON, YAML, `.env`, and URL queries |
| **Sensitive Headers** | `Authorization:`, `Cookie:`, `Proxy-Authorization:` |
| **PII** | Emails, Phone numbers, IBANs, Credit Cards (Luhn-validated) |

---

## 📦 Supported Agents & Tools

| Tool / Agent | Extraction Mode | Default Storage Target |
|---|---|---|
| **Claude Code** | Session history snapshots | JSON lines / state dumps |
| **Google Antigravity** | Agent trajectory & brain logs | Structured step dumps |
| **Cursor & Cursor Global** | Workspace & global chat database | SQLite state stores |
| **OpenCode** | Session traces & message logs | JSON history stores |
| **Cline / Roo-Code** | Task transcripts & prompt logs | Task state records |
| **OpenAI Codex CLI** | Session state records | CLI history files |
| **Zed AI / Zcode** | Conversation buffers | Editor history logs |

---

## 🚀 Quickstart

### Prerequisites
* **Python 3.8+** (Standard library only; no external dependencies).

### Direct Execution
```bash
# Harvest conversations across all enabled tools
python3 -m convo_harvester

# List available adapters and auto-detected paths
python3 -m convo_harvester --list

# Run a dry-run to preview actions without writing files
python3 -m convo_harvester --dry-run

# Harvest a specific tool only
python3 -m convo_harvester --tool claudecode

# Force full re-extraction (bypasses incremental timestamp checks)
python3 -m convo_harvester --full

# Custom output destination and configuration file
python3 -m convo_harvester --output /path/to/archive --config ./config.json
```

*(On Windows PowerShell or Command Prompt, use `python` instead of `python3`)*

### Optional Package Installation
```bash
pip install .
convo-harvester --list
```

---

## ⚙️ Configuration (`config.json`)

To customize active tools and output directories, copy `config.example.json` to `config.json`:

```json
{
  "output_dir": "harvest_output",
  "tools": {
    "claudecode":    { "enabled": true,  "path": null },
    "antigravity":   { "enabled": true,  "path": null },
    "cursor":        { "enabled": true,  "path": null },
    "opencode":      { "enabled": true,  "path": null },
    "cline":         { "enabled": true,  "path": null },
    "codex":         { "enabled": false, "path": null },
    "zcode":         { "enabled": false, "path": null }
  }
}
```

* `enabled` (`true`/`false`): Toggles harvesting for the specific tool.
* `path` (`null` or `string`): Set to `null` for multi-OS automatic discovery, or provide an explicit directory path override.
* `output_dir`: Target directory for generated Markdown archives.

### Directory Output Structure
```text
harvest_output/
├── claudecode/
│   ├── 2026-08-15_architecture_plan.md
│   └── 2026-08-16_api_refactor.md
├── antigravity/
│   └── task_trajectory_a02e1d.md
└── cursor/
    └── session_e4da5f.md
```

---

## ⏰ Automated Background Scheduling

To automate incremental backups on your workstation:

```bash
# Preview the scheduled task configuration
python3 install_scheduler.py

# Install daily background runner (default: 09:00 daily)
python3 install_scheduler.py --install

# Install with custom schedule time
python3 install_scheduler.py --install --time 22:30

# Remove background schedule
python3 install_scheduler.py --uninstall
```

* **Windows:** Registers a native Windows Scheduled Task (`ConvoHarvester` via `schtasks`).
* **macOS / Linux:** Configures a user-level `crontab` entry.

---

## 🧪 Test Suite

Unit tests validate all sanitization regex patterns and edge cases without external test runners:

```bash
python3 -m unittest discover -s tests -v
```

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
