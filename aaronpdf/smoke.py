#!/usr/bin/env python3
"""Checks that an AaronPDF site directory is safe to deploy.

Fails the build when branding leaked, a file is over Cloudflare's 25 MiB
asset limit, an Office/LibreOffice payload survived pruning, or the AGPL
source archive / security headers are missing.
"""
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_ASSET = 25 * 1024 * 1024
LANGS = "ar be ca da de es fa fr id it ja ko nl pl pt ru sk sv tr uk vi zh zh-TW".split()
OFFICE = [
    "word-to-pdf", "excel-to-pdf", "powerpoint-to-pdf", "odt-to-pdf", "ods-to-pdf",
    "odp-to-pdf", "odg-to-pdf", "rtf-to-pdf", "pages-to-pdf", "pub-to-pdf",
    "vsd-to-pdf", "wpd-to-pdf", "wps-to-pdf",
]
REMOVED = [
    "kura", "hyper-compress", "contact", "faq", "terms", "privacy", "licensing",
    "pdf-converter", "pdf-editor", "pdf-merge-split", "pdf-security",
]
SKIP_HTML_PREFIXES = ("pdfjs-viewer/", "pdfjs-annotation-viewer/", "docs/")


def fail(msg):
    print("smoke:", msg, file=sys.stderr)
    raise SystemExit(1)


def visible_bentopdf(html):
    """BentoPDF left in a page outside the AGPL credit footer and the about page."""
    parts = []
    i = 0
    lower = html
    while True:
        start = lower.find("<footer", i)
        if start < 0:
            parts.append(html[i:])
            break
        end = lower.find("</footer>", start)
        if end < 0:
            parts.append(html[i:])
            break
        parts.append(html[i:start])
        i = end + len("</footer>")
    return "BentoPDF" in "".join(parts) or "Bento PDF" in "".join(parts)


def main():
    if len(sys.argv) != 2:
        fail("usage: smoke.py SITE")
    site = Path(sys.argv[1])
    pdf = site / "pdf"
    required = [
        pdf / "index.html",
        pdf / "merge-pdf.html",
        pdf / "about.html",
        pdf / "404.html",
        pdf / "config.json",
        pdf / "LICENSE.txt",
        pdf / "apdf.css",
        pdf / "sw.js",
        pdf / "site.webmanifest",
        pdf / "images" / "favicon.svg",
        pdf / "images" / "favicon-no-bg.svg",
        pdf / "images" / "favicon-192x192.png",
        pdf / "images" / "favicon-512x512.png",
        pdf / "source" / "aaronpdf-source.tar.gz",
        site / "_headers",
        site / "_redirects",
    ]
    for path in required:
        if not path.is_file():
            fail(f"missing {path.relative_to(site)}")

    if (pdf / "libreoffice-wasm").exists():
        fail("pdf/libreoffice-wasm was not removed")
    for lang in LANGS:
        if (pdf / lang).exists():
            fail(f"translated pages were not removed: pdf/{lang}")
    for name in OFFICE + REMOVED:
        if (pdf / f"{name}.html").exists():
            fail(f"{name}.html should have been removed")
    if (pdf / "blog").exists():
        fail("pdf/blog was not removed")

    oversized = []
    for path in site.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".map"} or path.name.endswith(".d.ts"):
            fail(f"pruned file still present: {path.relative_to(site)}")
        size = path.stat().st_size
        if size > MAX_ASSET:
            oversized.append(f"{path.relative_to(site)} ({size} bytes)")
    if oversized:
        fail("asset over 25 MiB:\n" + "\n".join(oversized))

    index = (pdf / "index.html").read_text(encoding="utf-8", errors="replace")
    if "<title>AaronPDF - Private PDF tools in your browser</title>" not in index:
        fail("home page title was not rebranded")
    if "language-redirect-" in index or 'id="donation-ribbon"' in index:
        fail("home page still has the language redirect or donation ribbon")
    if 'content="noindex, nofollow"' not in index:
        fail("home page is missing the noindex robots meta tag")

    for path in pdf.rglob("*.html"):
        rel = str(path.relative_to(pdf))
        if rel.startswith(SKIP_HTML_PREFIXES) or rel == "about.html":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "BentoPDF" in text or "Bento PDF" in text:
            if visible_bentopdf(text):
                fail(f"visible BentoPDF outside the credit footer: pdf/{rel}")

    for path in (pdf / "assets").glob("*.js"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "BentoPDF" in text or "Bento PDF" in text:
            fail(f"BentoPDF remains in {path.relative_to(site)}")

    favicon = (pdf / "images" / "favicon.svg").read_text(encoding="utf-8")
    if "#E0A45C" not in favicon:
        fail("favicon.svg is not the amber AaronPDF monogram")

    manifest = json.loads((pdf / "site.webmanifest").read_text(encoding="utf-8"))
    if manifest.get("name") != "AaronPDF" or manifest.get("short_name") != "AaronPDF":
        fail(f"web manifest name is {manifest.get('name')!r}")

    config = json.loads((pdf / "config.json").read_text(encoding="utf-8"))
    disabled = set(config.get("disabledTools") or [])
    missing_tools = [name for name in OFFICE if name not in disabled]
    if missing_tools:
        fail("config.json disabledTools missing " + ", ".join(missing_tools))

    sw = (pdf / "sw.js").read_text(encoding="utf-8", errors="replace")
    if "aaronpdf-" not in sw:
        fail("service worker cache name was not bumped")

    headers = (site / "_headers").read_text(encoding="utf-8")
    for needle in (
        "X-Robots-Tag: noindex, nofollow",
        "Cross-Origin-Opener-Policy: same-origin",
        "Cross-Origin-Embedder-Policy: credentialless",
        "Content-Security-Policy:",
        "/pdf/assets/*",
        "Cache-Control: public, max-age=31536000, immutable",
    ):
        if needle not in headers:
            fail(f"_headers missing {needle}")
    for line in headers.splitlines():
        if len(line) > 2000:
            fail(f"_headers line exceeds Cloudflare's 2000 character limit ({len(line)})")

    redirects = (site / "_redirects").read_text(encoding="utf-8")
    for needle in ("/pdf/kura /pdf/ 302", "/pdf/blog /pdf/ 302", "/pdf/contact /pdf/about 302"):
        if needle not in redirects:
            fail(f"_redirects missing {needle}")

    archive = pdf / "source" / "aaronpdf-source.tar.gz"
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    for rel in ("aaronpdf-source/BUILD.txt", "aaronpdf-source/LICENSE", "aaronpdf-source/rebrand.py", "aaronpdf-source/README.md"):
        if rel not in names:
            fail(f"source archive missing {rel}")
    with tarfile.open(archive, "r:gz") as tar:
        note = tar.extractfile("aaronpdf-source/BUILD.txt").read().decode()
        license_text = tar.extractfile("aaronpdf-source/LICENSE").read().decode(errors="replace")
    if "GNU Affero General Public License" not in license_text:
        fail("source archive LICENSE is not the AGPL text")
    if "commit:" not in note or "https://github.com/AaronKatzin/bentopdf" not in note:
        fail("source archive BUILD.txt does not name the fork")
    about = (pdf / "about.html").read_text(encoding="utf-8", errors="replace")
    if "AaronKatzin/bentopdf" not in about or "/pdf/LICENSE.txt" not in about:
        fail("about page is missing the fork or AGPL link")
    if "github.com/AaronKatzin/bentopdf" not in index:
        fail("home page footer does not link this fork")

    print(f"smoke ok: {site}")


if __name__ == "__main__":
    main()
