#!/usr/bin/env python3
"""Package the AaronPDF corresponding-source archive into SITE/pdf/source/aaronpdf-source.tar.gz.

The archive is the aaronpdf/ tooling at this commit (rebrand, headers, Wrangler
config, license, README). The footer also links the full git tree, which is the
complete corresponding source of the modified program. Upload tokens are never
included; this script only packs the files listed below.
"""
import io
import os
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FILES = [
    "README.md",
    "rebrand.py",
    "prepare_site.py",
    "package_source.py",
    "smoke.py",
    "build.sh",
    "_headers",
    "_redirects",
    "wrangler.jsonc",
    "tools/serve.py",
]


def _commit():
    return os.environ.get("AARONPDF_COMMIT", "").strip() or "unknown"


def build_note(commit):
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tree = (
        f"https://github.com/AaronKatzin/bentopdf/tree/{commit}"
        if commit != "unknown"
        else "https://github.com/AaronKatzin/bentopdf"
    )
    return (
        "AaronPDF corresponding source\n"
        "license: GNU Affero General Public License v3.0 (AGPL-3.0-only)\n"
        "repository: https://github.com/AaronKatzin/bentopdf\n"
        f"commit: {commit}\n"
        f"tree: {tree}\n"
        "upstream: https://github.com/alam00000/bentopdf\n"
        f"packaged: {when}\n"
        "base: /pdf/\n"
        "\n"
        "This archive contains the AaronPDF modifications and the scripts that\n"
        "turn an unmodified BentoPDF build into the site served at\n"
        "https://aaronkatzin.com/pdf/. The complete corresponding source of the\n"
        "modified program is the git tree above.\n"
        "\n"
        "Rebuild from that commit:\n"
        "  npm ci\n"
        "  python3 -m pip install pillow\n"
        "  bash aaronpdf/build.sh\n"
        "  python3 aaronpdf/tools/serve.py aaronpdf/site 8080\n"
    ).encode()


def add_bytes(tar, name, data, mtime):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = mtime
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def add_file(tar, src, arcname, mtime):
    with open(src, "rb") as fh:
        data = fh.read()
    info = tar.gettarinfo(src, arcname)
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = mtime
    info.size = len(data)
    if arcname.endswith((".sh", "/serve.py", "/rebrand.py", "/prepare_site.py", "/package_source.py", "/smoke.py")):
        info.mode = 0o755
    tar.addfile(info, io.BytesIO(data))


def package(site, commit=None):
    commit = commit or _commit()
    out_dir = os.path.join(site, "pdf", "source")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "aaronpdf-source.tar.gz")
    # Fixed mtime so the archive does not change just because the clock did.
    mtime = 0
    with tarfile.open(out, "w:gz") as tar:
        add_bytes(tar, "aaronpdf-source/BUILD.txt", build_note(commit), mtime)
        add_file(tar, os.path.join(REPO, "LICENSE"), "aaronpdf-source/LICENSE", mtime)
        for rel in FILES:
            src = os.path.join(HERE, rel)
            if not os.path.isfile(src):
                raise SystemExit(f"source archive missing {rel}")
            add_file(tar, src, "aaronpdf-source/" + rel, mtime)
    print(out, os.path.getsize(out), commit)
    return out


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "site")
    package(site)


if __name__ == "__main__":
    main()
