#!/usr/bin/env python3
"""Install the viz MCP server and add it to Claude Desktop (3p mode) once the app has quit.

The server, widget.html and guide.md are copied to an install directory outside
the folders that macOS privacy protection (TCC) guards. Desktop starts MCP
servers from processes that may lack access to ~/Documents, ~/Desktop or
~/Downloads; a server read from a repository there fails at random with
"Operation not permitted". Symbolic links do not help: the target is checked.

Claude Desktop reads claude_desktop_config.json only at startup, keeps it in
memory and writes the whole file back while it runs, so an edit made while the
app is open is overwritten. This script detaches, waits until the app exits,
backs up the config, adds `mcpServers.viz`, and opens the app again. It changes
nothing if the app does not quit within 30 minutes.

Usage:
  python3 register.py [--dir DIR]          # install, then quit Claude Desktop with Cmd+Q
  python3 register.py [--dir DIR] --sync   # only copy edited files to the install directory
  python3 register.py [--dir DIR] --print  # only show the entry that would be added
DIR defaults to ~/.local/share/viz-widget. Log: /tmp/viz-register.log
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

CONFIG = os.path.expanduser("~/Library/Application Support/Claude-3p/claude_desktop_config.json")
APP_BIN = "/Applications/Claude.app/Contents/MacOS/Claude"
SRC = os.path.dirname(os.path.realpath(__file__))
RUNTIME_FILES = ("viz_widget_server.py", "widget.html", "guide.md")
DEFAULT_DIR = "~/.local/share/viz-widget"
# Folders under the home directory that TCC guards; network and removable
# volumes under /Volumes are guarded too.
PROTECTED = ("Documents", "Desktop", "Downloads", "Library/Mobile Documents", "Library/CloudStorage")
LOG = "/tmp/viz-register.log"
TIMEOUT_S = 30 * 60


def install_dir(path):
    path = os.path.realpath(os.path.expanduser(path))
    home = os.path.realpath(os.path.expanduser("~"))
    # The default APFS volume ignores case, and realpath keeps the case it was given.
    tops = [os.path.join(home, name) for name in PROTECTED] + ["/Volumes"]
    for top in tops:
        if path.lower() == top.lower() or path.lower().startswith(top.lower() + os.sep):
            sys.exit(f"{path} is inside {top}, which macOS privacy protection guards; choose another --dir")
    return path


def install(dest):
    """Copies the runtime files; each is replaced atomically, since the running
    server reads widget.html and guide.md on every request."""
    os.makedirs(dest, exist_ok=True)
    for name in RUNTIME_FILES:
        target = os.path.join(dest, name)
        if os.path.islink(target):
            os.unlink(target)  # an old link into the repository would be followed by copy2
        tmp = target + ".tmp-viz"
        shutil.copy2(os.path.join(SRC, name), tmp)
        os.replace(tmp, target)


def server_entry(dest):
    server = os.path.join(dest, "viz_widget_server.py")
    home = os.path.realpath(os.path.expanduser("~"))
    if server.startswith(home + os.sep):
        # In SSH sessions Desktop runs this same command on the remote host. A
        # $HOME-relative path lets one entry work on both machines when the files
        # sit at the same place under the home directory there.
        rel = os.path.relpath(server, home)
        return {"command": "/bin/sh", "args": ["-c", "exec python3 \"$HOME\"/" + shlex.quote(rel)]}
    return {"command": "/bin/sh", "args": ["-c", f"exec python3 {shlex.quote(server)}"]}


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S ") + msg + "\n")


def app_running():
    # pgrep cannot see the app's process from inside a Claude Code session; ps can.
    out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    return any(line.strip() == APP_BIN for line in out.stdout.splitlines())


def patch_config(entry):
    backup = CONFIG + time.strftime(".bak-viz-%Y%m%d-%H%M%S")
    shutil.copy2(CONFIG, backup)
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("mcpServers", {})["viz"] = entry
    tmp = CONFIG + ".tmp-viz"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)
    log(f"config patched; backup at {backup}")


def main(entry):
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
        patch_config(entry)
    except Exception as e:  # leave the config as it was and say why
        log(f"patch failed, config unchanged: {e!r}")
        return
    if app_running():
        log("WARNING: Claude started while patching; quit it once more and run this script again")
        return
    subprocess.run(["open", "-a", "Claude"])
    log("reopened Claude")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install the viz MCP server and register it in Claude Desktop (3p).")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"install directory (default {DEFAULT_DIR})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", action="store_true", help="only show the entry that would be added")
    mode.add_argument("--sync", action="store_true", help="only copy the runtime files to the install directory")
    mode.add_argument("--foreground", action="store_true", help="wait for the app to quit without detaching")
    opts = parser.parse_args()
    dest = install_dir(opts.dir)
    entry = server_entry(dest)
    if opts.print:
        print(json.dumps({"mcpServers": {"viz": entry}}, indent=2))
        sys.exit(0)
    install(dest)
    if opts.sync:
        print(f"copied {', '.join(RUNTIME_FILES)} to {dest}. guide.md applies at once; for "
              "viz_widget_server.py end the server process, for widget.html restart Desktop.")
        sys.exit(0)
    if not os.path.exists(CONFIG):
        sys.exit(f"{CONFIG} not found: is Claude Desktop set up in third-party (3p) mode?")
    if opts.foreground:
        main(entry)
        sys.exit(0)
    print("Quit Claude Desktop with Cmd+Q and do not reopen it: this script adds the viz "
          f"server ({dest}) and reopens the app. Progress: {LOG}")
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
    main(entry)
