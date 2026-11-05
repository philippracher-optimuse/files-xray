"""FilesXray: folder size viewer as a small local web app.

Start with:  python server.py
Then the browser opens at http://127.0.0.1:8765
Only reachable from this computer (bound to 127.0.0.1).
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
    denied = False
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError:
        entries = []
        denied = True

    for e in entries:
        if _is_real_dir(e):
            subdirs += 1
            child = scan(e.path)
            size += child["size"]
            total_files += child["total_files"]
            total_dirs += 1 + child["total_dirs"]
        else:
            try:
                if e.is_file(follow_symlinks=False):
                    size += e.stat(follow_symlinks=False).st_size
                    files += 1
                    total_files += 1
            except OSError:
                pass

    stats = {
        "size": size,
        "files": files,              # files directly in this folder
        "subdirs": subdirs,          # folders directly in this folder
        "total_files": total_files,  # files in this folder and all below
        "total_dirs": total_dirs,
        "denied": denied,
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
                    "empty": s["total_files"] == 0 and not s["denied"],
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
