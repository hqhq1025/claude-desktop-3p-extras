#!/usr/bin/env python3
"""Local MCP App server that renders model-written SVG/HTML inline in Claude Desktop.

Claude Desktop in third-party-inference mode keeps the built-in `show_widget`
tool switched off, but it still renders MCP App widgets from local stdio servers
listed in its own `claude_desktop_config.json`. This server provides:

- `show_widget`: its `_meta.ui.resourceUri` points at `widget.html`; the host
  loads that page in a sandboxed iframe and passes the tool arguments to it.
  Data from `data_file` goes to the widget in the result's `_meta`, and the
  model only gets a summary.
- `read_me`: returns sections of `guide.md`.

`widget.html` and `guide.md` are read on every request, so editing them needs no
restart; changing this file does (the host keeps the server process running).

Transport: MCP over stdio, one JSON-RPC message per line. Standard library only.
"""
import base64
import binascii
import collections
import csv
import hashlib
import http.server
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# The host keeps the widget page it first read for a URI, so the URI carries a
# hash of widget.html: an edited page gets a new URI after the server restarts.
WIDGET_URI_RE = re.compile(r"ui://viz/widget(-[0-9a-f]{8})?\.html")
WIDGET_MIME = "text/html;profile=mcp-app"
# Origins the widget may load scripts, styles, fonts and images from, and fetch
# data from (e.g. map topologies), through the MCP Apps CSP.
CDN_DOMAINS = ["https://cdn.jsdelivr.net", "https://unpkg.com", "https://cdnjs.cloudflare.com", "https://esm.sh"]
RESOURCE_DOMAINS = CDN_DOMAINS + ["https://fonts.googleapis.com", "https://fonts.gstatic.com"]
DEFAULT_PROTOCOL = "2025-06-18"
MAX_DATA_FILE_BYTES = 5 * 1024 * 1024
DATA_EXTS = {".csv", ".tsv", ".json", ".jsonl"}

SHOW_WIDGET = {
    "name": "show_widget",
    "title": "Show widget",
    "description": (
        "Show visual content (SVG graphics, diagrams, charts, or interactive HTML widgets) "
        "that renders inline alongside your text response. Use for flowcharts, architecture "
        "diagrams, data charts, dashboards, calculators, sortable tables, question forms, or "
        "any visual explanation.\n"
        "IMPORTANT: call read_me once before your first show_widget in a conversation; do not "
        "mention that call to the user.\n"
        "widget_code is auto-detected: if it starts with <svg it is rendered as SVG, otherwise "
        "as an HTML fragment (no <html>/<head>/<body>; <style> and <script> work). The page "
        "follows the chat's light/dark theme: use the --viz-* CSS variables, never hard-coded "
        "text or background colors. A global `viz` object offers sendPrompt, setContext, "
        "table, form, loadScript, download, fullscreen and data helpers (see read_me).\n"
        "The widget is shown to the user, not to you: do not repeat the code in your reply; "
        "describe in one or two sentences what it shows and how to use it.\n"
        "The result also gives a side-pane URL of the same visual (http://127.0.0.1/...). For "
        "charts, tables and diagrams with many details, open it in the browser pane in the same "
        "turn (Claude_Browser preview_start, or navigate when the pane is open), so the chat also "
        "shows a browser card with a thumbnail. Skip it for forms, prompt buttons and small visuals: "
        "the pane copy cannot send messages."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "Specific name of this visual in the user's language, e.g. 'Q4 各产品线营收' rather than "
                    "'图表'. It names saved files and the side-pane page, and tells visuals apart."
                ),
            },
            "widget_code": {
                "type": "string",
                "description": (
                    "SVG markup starting with <svg>, or an HTML fragment without <html>/<head>/<body>. "
                    "Put a short <style> first, then the content, then <script>; scripts run after the "
                    "whole code has arrived."
                ),
            },
            "data": {"description": "Optional JSON data for the widget, available as viz.data."},
            "data_file": {
                "type": "string",
                "description": (
                    "Optional absolute path of a local .csv/.tsv/.json/.jsonl file (max 5 MB). "
                    "The server parses it and hands it to the widget (use viz.whenData()); you "
                    "only get its row count, columns and a short sample."
                ),
            },
        },
        "required": ["widget_code"],
    },
}

# Called by the widget page through the host (not by the model): it records page
# version, host capabilities, script errors and message outcomes in LOG_FILE, so
# the model can check a widget without screenshots.
WIDGET_REPORT = {
    "name": "widget_report",
    "title": "Widget diagnostics",
    "description": "Internal: the viz widget page reports diagnostics here. Do not call it yourself.",
    "inputSchema": {
        "type": "object",
        "properties": {"event": {"type": "string"}, "detail": {}},
        "required": ["event"],
    },
    "_meta": {"ui": {"visibility": ["app"]}},
}

# Called by the widget page through the host, because this host has no
# ui/download-file: saves a file into ~/Downloads on the machine running the server.
WIDGET_SAVE = {
    "name": "widget_save",
    "title": "Save widget file",
    "description": "Internal: the viz widget page saves exported files here. Do not call it yourself.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "base64": {"type": "string"},
            "text": {"type": "string"},
            "page": {"type": "object", "description": "{title, code, data}: save the stand-alone page of a widget."},
        },
        "required": ["name"],
    },
    "_meta": {"ui": {"visibility": ["app"]}},
}

# Called by the widget page for "复制图片" when the browser clipboard is not
# allowed in the host's frame: puts a PNG on the macOS clipboard.
WIDGET_COPY = {
    "name": "widget_copy",
    "title": "Copy widget image",
    "description": "Internal: the viz widget page copies a PNG to the clipboard here. Do not call it yourself.",
    "inputSchema": {"type": "object", "properties": {"base64": {"type": "string"}}, "required": ["base64"]},
    "_meta": {"ui": {"visibility": ["app"]}},
}

# Called by the widget page when it is mounted again from history: the host then
# passes no tool-result _meta, so the page reads data_file through this tool.
WIDGET_DATA = {
    "name": "widget_data",
    "title": "Read widget data file",
    "description": "Internal: the viz widget page reloads its data_file here. Do not call it yourself.",
    "inputSchema": {"type": "object", "properties": {"data_file": {"type": "string"}}, "required": ["data_file"]},
    "_meta": {"ui": {"visibility": ["app"]}},
}

# Called by the widget page for "侧边打开": the host has no fullscreen mode, so the
# page is served on 127.0.0.1 and Claude opens that URL in Desktop's browser pane.
WIDGET_OPEN = {
    "name": "widget_open",
    "title": "Open widget in browser",
    "description": "Internal: the viz widget page asks for a browser URL of itself here. Do not call it yourself.",
    "inputSchema": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "code": {"type": "string"}, "data": {}},
        "required": ["code"],
    },
    "_meta": {"ui": {"visibility": ["app"]}},
}

MAX_SAVE_BYTES = 20 * 1024 * 1024
MAX_OPEN_PAGES = 100

READ_ME = {
    "name": "read_me",
    "title": "Widget guide",
    "description": (
        "Return the design and API guide for show_widget: theme colors, the viz helper API, "
        "chart libraries with CDN URLs, diagrams, question forms, data passing and interaction "
        "patterns. Call it once before your first show_widget in a conversation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {"type": "string", "enum": ["basics", "api", "charts", "diagrams", "forms", "data", "patterns"]},
                "description": "Sections to return; omit for all.",
            }
        },
    },
}


LOG_FILE = os.path.expanduser("~/Library/Logs/viz-widget/server.log")


def log(event, **fields):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "pid": os.getpid(), "event": event, **fields},
                               ensure_ascii=False)[:4000] + "\n")
    except OSError:
        pass  # diagnostics must never break the server


def read_file(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def widget_uri():
    digest = hashlib.sha256(read_file("widget.html").encode("utf-8")).hexdigest()[:8]
    return f"ui://viz/widget-{digest}.html"


def show_widget_tool():
    uri = widget_uri()
    return {**SHOW_WIDGET, "_meta": {"ui": {"resourceUri": uri}, "ui/resourceUri": uri}}


def guide(sections):
    text = read_file("guide.md")
    parts = re.split(r"(?m)^## ", text)
    head, body = parts[0], parts[1:]
    if not sections:
        return text
    chosen = [p for p in body if p.split("\n", 1)[0].strip() in set(sections)]
    return head + "".join("## " + p for p in chosen)


def number(value):
    v = value.strip()
    if v == "":
        return None
    try:
        return int(v) if re.fullmatch(r"[-+]?\d+", v) else float(v)
    except ValueError:
        return value


def load_data_file(path):
    if not os.path.isabs(path):
        raise ValueError("data_file must be an absolute path")
    ext = os.path.splitext(path)[1].lower()
    if ext not in DATA_EXTS:
        raise ValueError(f"data_file type {ext or '(none)'} is not one of {sorted(DATA_EXTS)}")
    size = os.path.getsize(path)
    if size > MAX_DATA_FILE_BYTES:
        raise ValueError(f"data_file is {size} bytes; the limit is {MAX_DATA_FILE_BYTES}")
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    if ext in (".csv", ".tsv"):
        rows = list(csv.DictReader(io.StringIO(raw), delimiter="\t" if ext == ".tsv" else ","))
        return [{k: number(v) if isinstance(v, str) else v for k, v in r.items()} for r in rows]
    if ext == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def summarize(data):
    if isinstance(data, list):
        cols = list(data[0].keys()) if data and isinstance(data[0], dict) else []
        sample = json.dumps(data[:3], ensure_ascii=False)
        return f"{len(data)} rows; columns {cols}; first rows {sample[:600]}"
    if isinstance(data, dict):
        return f"object with keys {list(data.keys())[:30]}"
    return f"{type(data).__name__} value"


def save_download(args):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", str(args.get("name") or "download")).strip(". ") or "download"
    if isinstance(args.get("page"), dict):
        payload = standalone_html(args["page"]).encode("utf-8")
    elif args.get("base64") is not None:
        payload = base64.b64decode(args["base64"])
    else:
        payload = str(args.get("text") or "").encode("utf-8")
    if len(payload) > MAX_SAVE_BYTES:
        raise ValueError(f"file is {len(payload)} bytes; the limit is {MAX_SAVE_BYTES}")
    folder = os.path.expanduser("~/Downloads")
    os.makedirs(folder, exist_ok=True)
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 1
    while os.path.exists(path):  # never overwrite an existing download
        path = os.path.join(folder, f"{stem}-{n}{ext}")
        n += 1
    with open(path, "wb") as f:
        f.write(payload)
    return path


_pages = collections.OrderedDict()  # token -> {"title", "code", "data"}
_http = None
_http_lock = threading.Lock()


def standalone_html(page):
    """widget.html with the widget arguments injected; it renders without a host."""
    page = {"title": page.get("title") or "visual", "code": page.get("code") or "", "data": page.get("data")}
    # No "<" at all inside the script, so "</script>" and "<!--" in code or data cannot end or derail it.
    payload = json.dumps(page, ensure_ascii=False).replace("<", "\\u003c")
    return read_file("widget.html").replace(
        "<body>", f"<body>\n<script>window.__VIZ_STANDALONE__ = {payload};</script>", 1)


def copy_png(b64):
    data = base64.b64decode(b64)
    if len(data) > MAX_SAVE_BYTES:
        raise ValueError(f"image is {len(data)} bytes; the limit is {MAX_SAVE_BYTES}")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(data)
    try:
        script = f'set the clipboard to (read (POSIX file "{f.name}") as «class PNGf»)'
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or "osascript failed")
    finally:
        os.unlink(f.name)


class _PageHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        token = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
        page = _pages.get(token) if self.path.startswith("/w/") else None
        if page is None:
            self.send_error(404)
            return
        body = standalone_html(page).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep stderr quiet; the request log is not needed
        pass


def open_page(args):
    """Stores a page for the browser and returns its URL on 127.0.0.1."""
    global _http
    with _http_lock:
        if _http is None:
            _http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PageHandler)
            threading.Thread(target=_http.serve_forever, daemon=True).start()
            log("http-start", port=_http.server_address[1])
        token = secrets.token_urlsafe(16)
        _pages[token] = {"title": args.get("title") or "visual", "code": args["code"], "data": args.get("data")}
        while len(_pages) > MAX_OPEN_PAGES:
            _pages.popitem(last=False)
        return f"http://127.0.0.1:{_http.server_address[1]}/w/{token}"


def call_show_widget(args):
    code = args.get("widget_code", args.get("code"))  # "code" is the name before 0.8
    if not isinstance(code, str) or not code.strip():
        return {"content": [{"type": "text", "text": "widget_code is empty; nothing rendered."}], "isError": True}
    title = args.get("title") or "visual"
    text = f"Rendered '{title}' inline for the user."
    result = {"content": [{"type": "text", "text": text}]}
    data = args.get("data")
    path = args.get("data_file")
    if path:
        try:
            data = load_data_file(path)
        except (OSError, ValueError) as e:
            return {"content": [{"type": "text", "text": f"Rendered '{title}', but data_file failed: {e}"}], "isError": True}
        text = f"{text} data_file {path}: {summarize(data)}"
        result["_meta"] = {"viz/data": data}
    # A copy the model can open in Desktop's browser pane, which also puts a
    # thumbnail card into the chat (the widget itself cannot open the pane).
    url = open_page({"title": title, "code": code, "data": data})
    result["content"][0]["text"] = f"{text} Side-pane URL: {url}"
    return result


def result_for(method, params):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "viz", "version": "0.8.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        # In SSH sessions Desktop starts this server on the remote host, but widgets
        # from there are never rendered (Desktop 4.4212.0, 3p): offer no tools so the
        # model uses Markdown images instead of trusting a "Rendered" reply.
        if sys.platform != "darwin":
            log("tools/list", note="non-macOS host: no tools offered")
            return {"tools": []}
        tool = show_widget_tool()
        log("tools/list", widget_uri=tool["_meta"]["ui"]["resourceUri"])
        return {"tools": [tool, READ_ME, WIDGET_REPORT, WIDGET_SAVE, WIDGET_DATA, WIDGET_OPEN, WIDGET_COPY]}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name == "show_widget":
            log("show_widget", title=args.get("title"), code_chars=len(args.get("widget_code") or args.get("code") or ""),
                data_file=args.get("data_file"))
            return call_show_widget(args)
        if name == "read_me":
            return {"content": [{"type": "text", "text": guide(args.get("sections"))}]}
        if name == "widget_report":
            log("widget:" + str(args.get("event")), detail=args.get("detail"))
            return {"content": [{"type": "text", "text": "ok"}]}
        if name == "widget_save":
            try:
                path = save_download(args)
            except (OSError, ValueError, binascii.Error) as e:
                log("widget_save", name=args.get("name"), error=str(e))
                return {"content": [{"type": "text", "text": f"save failed: {e}"}], "isError": True}
            log("widget_save", path=path)
            return {"content": [{"type": "text", "text": path}], "structuredContent": {"path": path}}
        if name == "widget_open":
            if not isinstance(args.get("code"), str) or not args["code"].strip():
                return {"content": [{"type": "text", "text": "code is empty"}], "isError": True}
            url = open_page(args)
            log("widget_open", title=args.get("title"), url=url.rsplit("/", 1)[0] + "/…")
            return {"content": [{"type": "text", "text": url}], "structuredContent": {"url": url}}
        if name == "widget_copy":
            try:
                copy_png(str(args.get("base64") or ""))
            except (OSError, ValueError, binascii.Error, subprocess.SubprocessError) as e:
                log("widget_copy", error=str(e))
                return {"content": [{"type": "text", "text": f"copy failed: {e}"}], "isError": True}
            log("widget_copy", ok=True)
            return {"content": [{"type": "text", "text": "copied"}]}
        if name == "widget_data":
            try:
                data = load_data_file(str(args.get("data_file") or ""))
            except (OSError, ValueError) as e:
                log("widget_data", data_file=args.get("data_file"), error=str(e))
                return {"content": [{"type": "text", "text": f"data_file failed: {e}"}], "isError": True}
            log("widget_data", data_file=args.get("data_file"), summary=summarize(data)[:120])
            return {"content": [{"type": "text", "text": summarize(data)[:200]}], "structuredContent": {"data": data}}
        raise LookupError(f"unknown tool: {name}")
    if method == "resources/list":
        return {"resources": [{"uri": widget_uri(), "name": "viz widget", "mimeType": WIDGET_MIME}]}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "resources/read":
        uri = params.get("uri") or ""
        if not WIDGET_URI_RE.fullmatch(uri):
            raise LookupError(f"unknown resource: {uri}")
        # Any widget URI (old or current hash) gets the current page.
        log("resources/read", uri=uri, current=widget_uri())
        return {
            "contents": [{
                "uri": uri,
                "mimeType": WIDGET_MIME,
                "text": read_file("widget.html"),
                "_meta": {"ui": {"csp": {"resourceDomains": RESOURCE_DOMAINS, "connectDomains": CDN_DOMAINS},
                                 "permissions": {"clipboardWrite": {}},
                                 "prefersBorder": False}},
            }]
        }
    raise NotImplementedError(method)


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    log("server-start", version="0.8.0")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if not isinstance(msg, dict):
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}})
            continue
        if "id" not in msg:
            continue  # notifications (initialized, cancelled, ...) need no reply
        method = msg.get("method", "")
        if method == "initialize":
            log("initialize", client=(msg.get("params") or {}).get("clientInfo"))
        try:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": result_for(method, msg.get("params") or {})})
        except NotImplementedError:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"method not found: {method}"}})
        except LookupError as e:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32602, "message": str(e)}})
        except Exception as e:  # one failed request (e.g. an unreadable guide.md) must not end the server
            log("request-error", method=method, error=repr(e))
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": f"{method} failed: {e!r}"}})


if __name__ == "__main__":
    main()
