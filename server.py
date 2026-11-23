"""FilesXray: folder size viewer as a small local web app.

Start with:  python server.py
Then the browser opens at http://127.0.0.1:8765
Only reachable from this computer (bound to 127.0.0.1).

Deleting: the only change the tool can make is removing EMPTY folders
(folders without a single file anywhere inside). It uses os.rmdir, which
Windows refuses for any folder that still contains something, so files
can never be deleted by this tool.
"""

import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 8765
# Start folder: the home folder of whoever runs the tool, e.g. C:\Users\<name>
DEFAULT_PATH = os.path.expanduser("~")
# Folder with index.html. Inside the .exe (PyInstaller) files are unpacked to sys._MEIPASS.
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

# Cache: normalized folder path -> stats dict. Filled while scanning,
# so opening a subfolder later is instant.
_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_real_dir(entry: os.DirEntry) -> bool:
    """True for normal folders; skips symlinks and Windows junctions (avoid loops)."""
    try:
        if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
            return False
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _stats_empty(s: dict) -> bool:
    """Empty = no file anywhere inside, nothing unreadable, no links."""
    return s["total_files"] == 0 and not s["any_denied"] and not s["any_link"]


def scan(path: str) -> dict:
    """Recursively compute size and counts of a folder, caching every subfolder."""
    k = _key(path)
    cached = _cache.get(k)
    if cached is not None:
        return cached

    size = 0
    files = 0
    subdirs = 0
    total_files = 0
    total_dirs = 0
    empty_dirs = 0  # folders below this one that contain no files at all
    denied = False
    any_denied = False  # this folder or any folder below could not be read
    any_link = False    # a symlink/junction somewhere inside (counts as content)
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError:
        entries = []
        denied = True
        any_denied = True

    for e in entries:
        if _is_real_dir(e):
            subdirs += 1
            child = scan(e.path)
            size += child["size"]
            total_files += child["total_files"]
            total_dirs += 1 + child["total_dirs"]
            any_denied = any_denied or child["any_denied"]
            any_link = any_link or child["any_link"]
            if _stats_empty(child):
                empty_dirs += 1 + child["total_dirs"]  # whole subtree is empty
            else:
                empty_dirs += child["empty_dirs"]
        else:
            try:
                if e.is_file(follow_symlinks=False):
                    size += e.stat(follow_symlinks=False).st_size
                    files += 1
                    total_files += 1
                else:
                    # Symlink, junction or something else: not counted as a file,
                    # but the folder is never treated as empty.
                    any_link = True
            except OSError:
                any_link = True

    stats = {
        "size": size,
        "files": files,              # files directly in this folder
        "subdirs": subdirs,          # folders directly in this folder
        "total_files": total_files,  # files in this folder and all below
        "total_dirs": total_dirs,
        "empty_dirs": empty_dirs,
        "denied": denied,
        "any_denied": any_denied,
        "any_link": any_link,
    }
    _cache[k] = stats
    return stats


def list_folder(path: str) -> dict:
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return {"error": f"Ordner nicht gefunden: {path}"}

    with _lock:
        own = scan(path)
        folders = []
        files = []
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError as exc:
            return {"error": f"Kein Zugriff: {exc}"}

        for e in entries:
            if _is_real_dir(e):
                s = scan(e.path)
                folders.append({
                    "name": e.name,
                    "path": e.path,
                    "size": s["size"],
                    "has_subdirs": s["subdirs"] > 0,
                    "subdirs": s["subdirs"],
                    "files": s["files"],
                    "total_files": s["total_files"],
                    # "empty" = no single file anywhere inside (may contain empty subfolders)
                    "empty": _stats_empty(s),
                    "empty_dirs": s["empty_dirs"],
                    "denied": s["denied"],
                })
            else:
                try:
                    if e.is_file(follow_symlinks=False):
                        files.append({
                            "name": e.name,
                            "path": e.path,
                            "size": e.stat(follow_symlinks=False).st_size,
                        })
                except OSError:
                    pass

    folders.sort(key=lambda f: f["size"], reverse=True)
    files.sort(key=lambda f: f["size"], reverse=True)
    parent = os.path.dirname(path)
    return {
        "path": path,
        "parent": parent if parent != path else None,
        "size": own["size"],
        "total_files": own["total_files"],
        "empty_dirs": own["empty_dirs"],
        "folders": folders,
        "files": files,
    }


def largest_files(path: str, limit: int = 25) -> dict:
    """The biggest files anywhere below `path`."""
    path = os.path.abspath(path)
    found = []
    for root, dirs, fnames in os.walk(path, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))
                   and not _is_junction_path(os.path.join(root, d))]
        for n in fnames:
            p = os.path.join(root, n)
            try:
                found.append((os.path.getsize(p), p))
            except OSError:
                pass
    found.sort(reverse=True)
    return {"files": [{"path": p, "size": s} for s, p in found[:limit]]}


def _is_protected(path: str) -> bool:
    """Folders that must never be removed themselves: drive roots and the home folder."""
    k = _key(path)
    return (os.path.dirname(k) == k                      # drive root like C:\\
            or k == _key(os.path.expanduser("~")))


def _remove_empty(path: str, remove_self: bool, dry_run: bool, deleted: list, errors: list) -> bool:
    """Delete empty folders below `path` (bottom-up). Returns True if `path` is now gone
    (or would be gone in a dry run). A folder counts as empty when no file is left inside,
    so a folder that only holds empty subfolders is removed as a whole."""
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError as exc:
        errors.append({"path": path, "error": str(exc)})
        return False

    has_content = False
    for e in entries:
        if _is_real_dir(e):
            if not _remove_empty(e.path, True, dry_run, deleted, errors):
                has_content = True
        else:
            has_content = True  # a file, symlink or junction: keep this folder

    if has_content or not remove_self or _is_protected(path):
        return False
    if not dry_run:
        try:
            os.rmdir(path)  # fails if anything is still inside: files are never deleted
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
            return False
    deleted.append(path)
    return True


def delete_empty(path: str, remove_self: bool, dry_run: bool) -> dict:
    """remove_self=False: all empty folders anywhere below `path` (path itself stays).
    remove_self=True: `path` itself plus everything below, if it holds no files."""
    path = os.path.abspath(path)
    if not os.path.isdir(path) or os.path.islink(path) or _is_junction_path(path):
        return {"error": f"Ordner nicht gefunden: {path}"}
    if remove_self and _is_protected(path):
        return {"error": f"Dieser Ordner wird aus Sicherheitsgründen nicht gelöscht: {path}"}

    deleted: list[str] = []
    errors: list[dict] = []
    with _lock:
        _remove_empty(path, remove_self, dry_run, deleted, errors)
        if not dry_run:
            # Forget cached sizes for this folder, everything below and every parent,
            # so the next view shows the new state. Sibling folders stay cached.
            k = _key(path)
            for key in list(_cache):
                if key == k or key.startswith(k.rstrip("\\/") + os.sep) or k.startswith(key.rstrip("\\/") + os.sep):
                    _cache.pop(key, None)
    # Show the topmost folders first (a removed parent includes its children).
    deleted.sort(key=lambda p: (p.count(os.sep), p.lower()))
    return {"dry_run": dry_run, "count": len(deleted), "deleted": deleted, "errors": errors}


def _is_junction_path(p: str) -> bool:
    try:
        return os.path.isjunction(p)
    except (AttributeError, OSError):
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data):
        self._send(json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        p = q.get("path", [DEFAULT_PATH])[0]

        if url.path == "/":
            html = (HERE / "index.html").read_text(encoding="utf-8")
            html = html.replace("__DEFAULT_PATH__", json.dumps(DEFAULT_PATH))
            self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/api/list":
            self._json(list_folder(p))
        elif url.path == "/api/largest":
            self._json(largest_files(p))
        elif url.path == "/api/refresh":
            with _lock:
                _cache.clear()
            self._json({"ok": True})
        elif url.path == "/api/open":
            # Opens the folder in Windows Explorer (or selects the file).
            if os.path.isdir(p):
                os.startfile(p)
            elif os.path.isfile(p):
                subprocess.Popen(["explorer", "/select,", p])
            self._json({"ok": True})
        else:
            self._send(b"Not found", "text/plain", 404)

    def do_POST(self):
        # Changes only via POST with our own header: browsers do not let other
        # websites send this header to 127.0.0.1 without permission (CORS),
        # so no foreign page can trigger a delete.
        if self.headers.get("X-FilesXray") != "1":
            self._send(b"Forbidden", "text/plain", 403)
            return
        url = urlparse(self.path)
        q = parse_qs(url.query)
        p = q.get("path", [""])[0]
        if url.path == "/api/delete-empty":
            mode = q.get("mode", ["below"])[0]          # "below" or "self"
            dry = q.get("dry", ["0"])[0] == "1"
            self._json(delete_empty(p, remove_self=(mode == "self"), dry_run=dry))
        else:
            self._send(b"Not found", "text/plain", 404)


class Server(ThreadingHTTPServer):
    # On Windows, address reuse lets two programs share one port silently.
    # Disable it so a busy port raises an error and we move to the next one.
    allow_reuse_address = False
    daemon_threads = True


def main():
    # Try the default port; if it is taken (e.g. tool already running), use the next free one.
    for port in range(PORT, PORT + 20):
        try:
            server = Server((HOST, port), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit("Kein freier Port gefunden.")
    url = f"http://{HOST}:{port}"
    print(f"FilesXray laeuft auf {url}  (Beenden: Strg+C oder Fenster schliessen)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
