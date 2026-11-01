#!/usr/bin/env python3
"""Add the viz MCP server to Claude Desktop (3p mode) once the app has quit.

Claude Desktop reads claude_desktop_config.json only at startup, keeps it in
memory and writes the whole file back while it runs, so an edit made while the
app is open is overwritten. This script detaches, waits until the app exits,
backs up the config, adds `mcpServers.viz`, and opens the app again. It changes
nothing if the app does not quit within 30 minutes.

Usage:
  python3 register.py            # then quit Claude Desktop with Cmd+Q
  python3 register.py --print    # only show the entry that would be added
Log: /tmp/viz-register.log
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

CONFIG = os.path.expanduser("~/Library/Application Support/Claude-3p/claude_desktop_config.json")
APP_BIN = "/Applications/Claude.app/Contents/MacOS/Claude"
SERVER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "viz_widget_server.py")
LOG = "/tmp/viz-register.log"
TIMEOUT_S = 30 * 60


def server_entry():
    home = os.path.expanduser("~")
    if SERVER.startswith(home + os.sep):
        # In SSH sessions Desktop runs this same command on the remote host. A
        # $HOME-relative path lets one entry work on both machines when the files
        # sit at the same place under the home directory there.
        rel = os.path.relpath(SERVER, home)
        return {"command": "/bin/sh", "args": ["-c", f'exec python3 "$HOME/{rel}"']}
    return {"command": "/bin/sh", "args": ["-c", f"exec python3 {shlex.quote(SERVER)}"]}


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + msg + "\n")


def app_running():
    # pgrep cannot see the app's process from inside a Claude Code session; ps can.
    out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    return any(line.strip() == APP_BIN for line in out.stdout.splitlines())


def patch_config():
    backup = CONFIG + time.strftime(".bak-viz-%Y%m%d-%H%M%S")
    shutil.copy2(CONFIG, backup)
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("mcpServers", {})["viz"] = server_entry()
    tmp = CONFIG + ".tmp-viz"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)
    log(f"config patched; backup at {backup}")


def main():
    log("waiting for Claude to quit")
    deadline = time.time() + TIMEOUT_S
    while True:
        while app_running():
            if time.time() > deadline:
                log("timeout: Claude did not quit; config unchanged")
                return
            time.sleep(0.5)
        # If the app is reopened before the patch lands, the new instance loads the
        # old config and writes it back, so patch at once and re-check first.
        if not app_running():
            break
        log("Claude was reopened before the patch; waiting for the next quit")
    try:
        patch_config()
    except Exception as e:  # leave the config as it was and say why
        log(f"patch failed, config unchanged: {e!r}")
        return
    if app_running():
        log("WARNING: Claude started while patching; quit it once more and run this script again")
        return
    subprocess.run(["open", "-a", "Claude"])
    log("reopened Claude")


if __name__ == "__main__":
    if "--print" in sys.argv:
        print(json.dumps({"mcpServers": {"viz": server_entry()}}, indent=2))
        sys.exit(0)
    if not os.path.exists(CONFIG):
        sys.exit(f"{CONFIG} not found: is Claude Desktop set up in third-party (3p) mode?")
    if "--foreground" in sys.argv:
        main()
        sys.exit(0)
    print("Quit Claude Desktop with Cmd+Q and do not reopen it: this script adds the viz "
          f"server and reopens the app. Progress: {LOG}")
    # Double fork into a new session, so that quitting the app (which also ends a
    # Claude Code session this was started from) does not stop the watcher.
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    main()
