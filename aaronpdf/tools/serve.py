#!/usr/bin/env python3
"""Local preview of an AaronPDF site directory.

Approximates the Cloudflare Workers static-asset setup used in production:
_redirects, _headers, html_handling auto-trailing-slash, and not_found_handling
404-page (nearest 404.html, which is pdf/404.html for /pdf/*).

  python3 aaronpdf/tools/serve.py aaronpdf/site 8080
  open http://127.0.0.1:8080/pdf/
"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".webmanifest": "application/manifest+json",
    ".pdf": "application/pdf",
    ".gz": "application/gzip",
    ".map": "application/json",
}


def load_header_blocks(path):
    if not path.is_file():
        return []
    blocks = []
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[:1].isspace():
            current = [raw.strip(), []]
            blocks.append(current)
        elif current is not None:
            current[1].append(raw.strip())
    return blocks


def load_redirects(path):
    rules = []
    if not path.is_file():
        return rules
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        bits = line.split()
        if len(bits) < 3:
            continue
        rules.append((bits[0], bits[1], int(bits[2])))
    return rules


def splat_match(pattern, path):
    """Match a Cloudflare path pattern. A single * consumes the rest, including slashes."""
    if "*" not in pattern:
        return path == pattern
    if pattern.count("*") > 1:
        return False
    pre, post = pattern.split("*", 1)
    if not path.startswith(pre) or not path.endswith(post):
        return False
    if post and len(path) < len(pre) + len(post):
        return False
    return True


REDIRECTS = load_redirects(ROOT / "_redirects")
HEADER_RULES = load_header_blocks(ROOT / "_headers")


def lookup_redirect(path):
    for pattern, dest, status in REDIRECTS:
        if not splat_match(pattern, path):
            continue
        if "*" in pattern and ":splat" in dest:
            pre, post = pattern.split("*", 1)
            middle = path[len(pre): len(path) - len(post) if post else None]
            dest = dest.replace(":splat", middle)
        return status, dest
    return None


def headers_for(path):
    found = {}
    for pattern, lines in HEADER_RULES:
        if not splat_match(pattern, path):
            continue
        for line in lines:
            if line.startswith("! "):
                found.pop(line[2:].strip().lower(), None)
                continue
            name, _, value = line.partition(":")
            if not value:
                continue
            found[name.strip().lower()] = (name.strip(), value.strip())
    return {name: value for name, value in found.values()}


def safe_file(rel):
    candidate = (ROOT / rel.lstrip("/")).resolve()
    if ROOT not in candidate.parents and candidate != ROOT:
        return None
    if candidate.name in {"_headers", "_redirects"}:
        return None
    return candidate if candidate.is_file() else None


def resolve_asset(path):
    """auto-trailing-slash: directories gain a slash, extensionless HTML does not."""
    if path != "/" and path.endswith("/"):
        index = safe_file(path + "index.html")
        if index:
            return index, 200, None
        trimmed = path.rstrip("/")
        html = safe_file(trimmed + ".html")
        if html:
            return None, 307, trimmed
    else:
        direct = safe_file(path)
        if direct:
            return direct, 200, None
        html = safe_file(path + ".html")
        index = safe_file(path + "/index.html")
        if index and not html:
            return None, 307, path + "/"
        if html:
            return html, 200, None
        if index:
            return None, 307, path + "/"
    return None, None, None


def nearest_404(path):
    parts = [part for part in path.split("/") if part]
    while True:
        rel = "/".join(parts + ["404.html"]) if parts else "404.html"
        found = safe_file("/" + rel)
        if found:
            return found
        if not parts:
            return None
        parts.pop()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_HEAD(self):
        self._respond(write_body=False)

    def do_GET(self):
        self._respond(write_body=True)

    def _respond(self, write_body):
        path = unquote(urlsplit(self.path).path or "/")
        if "\0" in path or any(part == ".." for part in path.split("/")):
            self.send_error(400)
            return
        redir = lookup_redirect(path)
        if redir:
            status, dest = redir
            self._send(status, b"", {"Location": dest, "Content-Type": "text/plain; charset=utf-8"}, path)
            return
        file, status, dest = resolve_asset(path)
        if dest:
            self._send(status, b"", {"Location": dest, "Content-Type": "text/plain; charset=utf-8"}, path)
            return
        if file is None:
            file = nearest_404(path)
            status = 404
        if file is None:
            self._send(404, b"Not found\n", {"Content-Type": "text/plain; charset=utf-8"}, path)
            return
        data = file.read_bytes() if write_body else b""
        ctype = TYPES.get(file.suffix.lower(), "application/octet-stream")
        self._send(status, data if write_body else b"", {"Content-Type": ctype}, path, body_len=file.stat().st_size if not write_body else None)

    def _send(self, status, body, extra, request_path, body_len=None):
        payload = body if isinstance(body, bytes) else body.encode()
        length = body_len if body_len is not None else len(payload)
        headers = headers_for(request_path)
        headers.update(extra)
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if payload and self.command != "HEAD":
            self.wfile.write(payload)


def main():
    if not (ROOT / "pdf" / "index.html").is_file():
        sys.exit(f"missing {ROOT / 'pdf' / 'index.html'}")
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"AaronPDF preview at http://127.0.0.1:{PORT}/pdf/", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
