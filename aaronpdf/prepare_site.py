#!/usr/bin/env python3
"""Turn an assembled BentoPDF dist tree into the AaronPDF site directory.

  python3 aaronpdf/prepare_site.py dist-publish aaronpdf/site

SRC is the output of scripts/assemble-dist-branch.mjs (it contains pdf/ and
index.html, and a generated _headers). DEST is what Wrangler uploads.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from package_source import package  # noqa: E402
from rebrand import rebrand_site, resolve_commit  # noqa: E402


def root_csp(text):
    in_root = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace():
            in_root = stripped == "/*"
            continue
        if in_root and stripped.startswith("Content-Security-Policy:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def directive_tokens(csp, name):
    for part in csp.split(";"):
        bits = part.strip().split()
        if bits and bits[0] == name:
            return set(bits[1:])
    return set()


def check_csp(built_headers, ours):
    """Fail when the app build allows a host this deployment's _headers does not."""
    if not built_headers.is_file():
        print("no built _headers; skipped CSP drift check")
        return
    built = root_csp(built_headers.read_text(encoding="utf-8"))
    current = root_csp(ours.read_text(encoding="utf-8"))
    if not built or not current:
        raise SystemExit("could not read the root Content-Security-Policy")
    missing = []
    for name in ("script-src", "connect-src", "worker-src", "font-src"):
        extra = directive_tokens(built, name) - directive_tokens(current, name)
        if extra:
            missing.append(f"{name}: {' '.join(sorted(extra))}")
    if missing:
        raise SystemExit(
            "aaronpdf/_headers is missing CSP sources the build now requires.\n"
            "Update aaronpdf/_headers (keep X-Robots-Tag and the /pdf/assets/* cache rule),\n"
            "then rebuild.\n" + "\n".join(missing)
        )
    print("CSP covers the built script-src and connect-src")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_site.py SRC_SITE DEST_SITE")
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    if not (src / "pdf" / "index.html").is_file():
        raise SystemExit(f"{src} has no pdf/index.html; run assemble-dist-branch.mjs first")
    commit = resolve_commit()
    check_csp(src / "_headers", HERE / "_headers")
    rebrand_site(src, dest, HERE.parent / "LICENSE", commit)
    shutil.copyfile(HERE / "_headers", dest / "_headers")
    shutil.copyfile(HERE / "_redirects", dest / "_redirects")
    package(str(dest), commit)
    print("prepared", dest, "commit", commit)


if __name__ == "__main__":
    main()
