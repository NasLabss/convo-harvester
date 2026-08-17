#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_scheduler.py — schedules the daily automatic run of the harvester.

  python install_scheduler.py            # shows what WOULD be installed (does nothing)
  python install_scheduler.py --install  # installs the task (schtasks Windows / cron Unix)
  python install_scheduler.py --uninstall
  python install_scheduler.py --install --time 21:30

The harvester is run via the package: `python -m convo_harvester`
(from the root of the convo-harvester-public/ project).

For safety, without --install it only DISPLAYS the command. The agent
or the user triggers the actual installation.

Windows -> Task Scheduler (schtasks), task "ConvoHarvester".
macOS/Linux -> user crontab, line marked "# ConvoHarvester".
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ENTRY = SCRIPT_DIR / "convo_harvester" / "__main__.py"
TASK_NAME = "ConvoHarvester"


def python_exe():
    return sys.executable or "python"


def run_command():
    """Harvester command: python -m convo_harvester (from the project root)."""
    return [python_exe(), "-m", "convo_harvester"]


def run_command_str():
    return " ".join(f'"{part}"' for part in run_command())


# ----------------------------- Windows ------------------------------------- #

def win_create_cmd(time):
    return ["schtasks", "/create", "/tn", TASK_NAME, "/tr", run_command_str(),
            "/sc", "daily", "/st", time, "/f"]


def win_delete_cmd():
    return ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]


# ----------------------------- Unix (cron) --------------------------------- #

def cron_line(time):
    hh, mm = time.split(":")
    return (f"{int(mm)} {int(hh)} * * * "
            f"{run_command_str()} >/dev/null 2>&1  # {TASK_NAME}")


def read_crontab():
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except FileNotFoundError:
        return None


def write_crontab(content):
    p = subprocess.run(["crontab", "-"], input=content, text=True)
    return p.returncode == 0


def cron_without_task(existing):
    return "\n".join(l for l in existing.splitlines()
                     if f"# {TASK_NAME}" not in l)


# ----------------------------- Actions ------------------------------------- #

def do_install(time):
    system = platform.system()
    if system == "Windows":
        cmd = win_create_cmd(time)
        print("Command:", " ".join(cmd))
        r = subprocess.run(cmd)
        if r.returncode == 0:
            print(f"OK — task '{TASK_NAME}' installed (daily at {time}).")
        else:
            print("schtasks failed (admin rights required?).")
        return r.returncode
    else:
        existing = read_crontab()
        if existing is None:
            print("`crontab` not found. Install cron or schedule manually:")
            print("   " + cron_line(time))
            return 1
        new = cron_without_task(existing).rstrip()
        new = (new + "\n" if new else "") + cron_line(time) + "\n"
        if write_crontab(new):
            print(f"OK — cron entry installed (daily at {time}).")
            print("   " + cron_line(time))
            return 0
        print("Failed to write crontab.")
        return 1


def do_uninstall():
    system = platform.system()
    if system == "Windows":
        r = subprocess.run(win_delete_cmd())
        print("Task removed." if r.returncode == 0 else "No task / failure.")
        return r.returncode
    else:
        existing = read_crontab()
        if not existing:
            print("No crontab.")
            return 0
        write_crontab(cron_without_task(existing).rstrip() + "\n")
        print("Cron entry removed.")
        return 0


def show_plan(time):
    system = platform.system()
    print(f"Platform: {system}")
    print(f"Harvester: {run_command_str()}  (from {SCRIPT_DIR})")
    print(f"Python: {python_exe()}")
    print(f"Time: {time} (daily)\n")
    if system == "Windows":
        print("WOULD run (add --install to do it):")
        print("   " + " ".join(win_create_cmd(time)))
    else:
        print("WOULD be added to the crontab (add --install to do it):")
        print("   " + cron_line(time))


def main():
    ap = argparse.ArgumentParser(description="Daily auto-run of the harvester.")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--time", default="09:00", help="HH:MM (default 09:00)")
    args = ap.parse_args()

    if not PACKAGE_ENTRY.exists():
        print(f"[!] convo_harvester package not found next to ({PACKAGE_ENTRY}).")
        return 1
    if args.uninstall:
        return do_uninstall()
    if args.install:
        return do_install(args.time)
    show_plan(args.time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
