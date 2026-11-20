#!/usr/bin/env python3
"""
AaronPDF rebrand of a BentoPDF static build (dist branch, BASE_URL=/pdf/).

AaronPDF is a modified version of BentoPDF (https://github.com/alam00000/bentopdf),
licensed under the GNU AGPL-3.0. This script IS the modification: it turns an
unmodified BentoPDF dist build into the AaronPDF site. It is re-runnable on future
upstream builds (it is idempotent on a fresh copy; always run it on a fresh copy).

Usage:
  python3 rebrand.py SRC_SITE DEST_SITE [--license LICENSE] [--source-archive FILE]

  SRC_SITE   root of an unmodified dist checkout (contains pdf/ and index.html)
  DEST_SITE  output dir (deleted and recreated)

Steps:
  1. copy SRC -> DEST and slim it (drop translated page sets, LibreOffice WASM,
     source maps, .d.ts files)
  2. rebrand display strings BentoPDF -> AaronPDF (HTML, JS UI strings, locale JSON,
     web manifest), never touching URLs, storage keys or code identifiers
  3. replace header nav + footer on every page; footer carries the AGPL notice/credit
  4. remove marketing: donation ribbon, "used by" logos, stats, compliance badges,
     testimonials/reviews, home FAQ, JSON-LD (incl. any rating markup), social links,
     upstream products (Kura, Hyper Compress), blog, company pages, SEO hub pages
  5. disable LibreOffice-based Office->PDF tools (config.json disabledTools)
  6. new About & License page, LICENSE.txt, monogram favicon set
"""
import json, os, re, shutil, sys, argparse, html
from pathlib import Path

BRAND = "AaronPDF"
TAGLINE = "Private PDF tools that run entirely in your browser."
UPSTREAM = "https://github.com/alam00000/bentopdf"
UPSTREAM_AUTHOR = "https://github.com/alam00000"
FORK = "https://github.com/AaronKatzin/bentopdf"
SITE_URL = "https://aaronkatzin.com/pdf/"
MODIFIED = "Nov 2026"

def resolve_commit():
    """Commit the deployed site was built from. CI sets AARONPDF_COMMIT; locally, use git."""
    env = os.environ.get("AARONPDF_COMMIT", "").strip()
    if env:
        return env
    import subprocess
    try:
        root = Path(__file__).resolve().parent.parent
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"

def source_tree_url(commit):
    if commit and commit != "unknown":
        return f"{FORK}/tree/{commit}"
    return FORK
ACCENT = "#E0A45C"   # aaronkatzin.com accent
BG = "#131210"

LANGS = "ar be ca da de es fa fr id it ja ko nl pl pt ru sk sv tr uk vi zh zh-TW".split()
# LibreOffice-WASM based converters (WASM is >25 MB/file, can't be hosted on Workers assets)
OFFICE_TOOLS = ["word-to-pdf", "excel-to-pdf", "powerpoint-to-pdf", "odt-to-pdf", "ods-to-pdf",
                "odp-to-pdf", "odg-to-pdf", "rtf-to-pdf", "pages-to-pdf", "pub-to-pdf",
                "vsd-to-pdf", "wpd-to-pdf", "wps-to-pdf"]
# upstream marketing / company / other-product pages removed from this deployment
REMOVED_PAGES = ["kura", "hyper-compress", "contact", "faq", "terms", "privacy", "licensing",
                 "pdf-converter", "pdf-editor", "pdf-merge-split", "pdf-security"]
REMOVED_DIRS = ["blog"]
REMOVED_FILES = ["funding.json", ".well-known/funding-manifest-urls",
                 "images/author-alam.jpg", "images/nvidia-inception.svg", "images/vultr-logo-dark.svg",
                 "images/vultr-logo-light.svg", "images/gdpr.svg", "images/ccpa.svg", "images/hipaa.svg",
                 "images/badge.svg", "images/bentopdf-tools.png", "images/og-tools.png",
                 "images/og-pdf-converter.png", "images/og-pdf-editor.png", "images/og-pdf-merge-split.png",
                 "images/og-pdf-security.png"]
SOCIAL_HOSTS = r"(?:ko-fi\.com|github\.com/sponsors|discord\.gg|discord\.com|instagram\.com|linkedin\.com|x\.com|twitter\.com|polar\.sh|buymeacoffee\.com|www\.bentopdf\.com/docs|bentopdf\.com/docs)"

# ---------------------------------------------------------------- helpers
def rd(p): return Path(p).read_text(encoding="utf-8", errors="surrogateescape")
def wr(p, s): Path(p).write_text(s, encoding="utf-8", errors="surrogateescape")

def element_span(s, start):
    """Return (start, end) of the balanced element whose start tag begins at s[start]."""
    m = re.match(r"<([a-zA-Z0-9]+)", s[start:])
    tag = m.group(1)
    pat = re.compile(r"<(/?)%s\b[^>]*?(/?)>" % tag, re.I)
    depth = 0
    for mm in pat.finditer(s, start):
        if mm.group(1): depth -= 1
        elif not mm.group(2): depth += 1
        if depth == 0:
            return start, mm.end()
    raise ValueError("unbalanced <%s> at %d" % (tag, start))

def remove_by_marker(s, marker, tag=None, replacement=""):
    """Remove the element containing attribute marker (e.g. 'id="x"'), or the first <tag after marker."""
    while True:
        i = s.find(marker)
        if i < 0: return s
        if tag:   # marker is a comment etc; remove next <tag
            j = s.find("<" + tag, i)
            if j < 0: return s
            a, b = element_span(s, j)
            s = s[:i] + replacement + s[b:]
        else:
            a = s.rfind("<", 0, i)
            a, b = element_span(s, a)
            s = s[:a] + replacement + s[b:]
        if replacement and marker in replacement: return s

def page_url(rel):
    p = rel[:-5] if rel.endswith(".html") else rel
    if p == "index": p = ""
    return SITE_URL + p

def tool_card_pattern():
    alt = "|".join(map(re.escape, OFFICE_TOOLS + REMOVED_PAGES))
    return re.compile(r'<a\b[^>]*href="/pdf/(?:%s)(?:\.html)?(?:[#?][^"]*)?"[^>]*>.*?</a>' % alt, re.S)

# ---------------------------------------------------------------- fragments
def credit_html(commit):
    return f"""<div class="apdf-credit">
<p><strong>{BRAND}</strong> is a modified version of <a href="{UPSTREAM}" target="_blank" rel="noopener">BentoPDF</a>
by <a href="{UPSTREAM_AUTHOR}" target="_blank" rel="noopener">alam00000</a> and contributors, modified by Aaron Katzin ({MODIFIED}).
It is free software under the <a href="/pdf/LICENSE.txt">GNU Affero General Public License v3.0</a> and comes with no warranty.
It is not affiliated with or endorsed by BentoPDF.</p>
<p>Source code: <a href="/pdf/source/aaronpdf-source.tar.gz">this version's modifications</a> &middot;
<a href="{source_tree_url(commit)}" target="_blank" rel="noopener">full source (fork)</a> &middot;
<a href="{UPSTREAM}" target="_blank" rel="noopener">original BentoPDF</a> &middot;
<a href="/pdf/about#license">license &amp; third-party notices</a></p>
</div>"""

def nav_html(mobile_button):
    links = [("/pdf/#tools-header", "All Tools"), ("/pdf/about", "About &amp; License")]
    desk = "\n".join(f'<a href="{h}" class="nav-link">{t}</a>' for h, t in links)
    mob = "\n".join(f'<a href="{h}" class="mobile-nav-link">{t}</a>' for h, t in links)
    return f"""<nav class="bg-gray-900 border-b border-white/10 sticky top-0 z-30 apdf-nav">
<div class="container mx-auto px-4">
<div class="flex justify-between items-center h-16">
<div class="flex-shrink-0 flex items-center cursor-pointer" id="home-logo">
<img id="nav-logo" src="/pdf/images/favicon-no-bg.svg" alt="{BRAND} logo" class="h-8 w-8">
<span id="nav-brand" class="text-white font-bold text-xl ml-2"><a href="/pdf/">{BRAND}</a></span>
</div>
<div class="hidden lg:flex flex-1 items-center justify-end space-x-2 xl:space-x-8">
{desk}
</div>
<div class="lg:hidden flex items-center gap-4">
{mobile_button}
</div>
</div>
</div>
<div id="mobile-menu" class="hidden lg:hidden bg-gray-900 border-t border-white/10">
<div class="px-2 pt-2 pb-3 space-y-1 text-center">
{mob}
</div>
</div>
</nav>"""

def footer_html(version, commit):
    return f"""<footer class="border-t border-white/10 py-10 apdf-footer">
<div class="container mx-auto px-4">
<div class="flex flex-col md:flex-row md:justify-between gap-6 text-center md:text-left">
<div>
<div class="flex items-center justify-center md:justify-start mb-3">
<img id="footer-logo" src="/pdf/images/favicon-no-bg.svg" alt="{BRAND} logo" class="h-9 w-9 mr-3">
<span id="footer-brand" class="text-xl font-bold text-white">{BRAND}</span>
</div>
<p id="footer-copyright" class="text-gray-400 text-sm">{TAGLINE}</p>
<p class="text-gray-500 text-xs mt-2">Version <span id="app-version">{version}</span> (based on BentoPDF {version})</p>
</div>
<ul class="space-y-2 text-gray-400 text-sm">
<li><a href="/pdf/#tools-header">All Tools</a></li>
<li><a href="/pdf/about">About &amp; License</a></li>
<li><a href="/pdf/wasm-settings">Advanced Settings</a></li>
<li><a href="/pdf/source/aaronpdf-source.tar.gz">Source Code</a></li>
</ul>
</div>
{credit_html(commit)}
</div>
</footer>"""

def compact_footer_html(commit):
    short = commit[:7] if commit and commit != "unknown" else "fork"
    return f"""<footer class="flex-none border-t border-gray-700 bg-gray-800 px-3 sm:px-4 py-2 text-[11px] sm:text-xs text-gray-500 apdf-footer apdf-footer--compact">
<nav class="flex flex-wrap items-center justify-center sm:justify-start gap-x-3 gap-y-0.5" aria-label="Site links">
<a href="/pdf/" class="hover:text-gray-200">{BRAND}</a>
<a href="/pdf/about" class="hover:text-gray-200">About &amp; License</a>
<span>Modified version of <a href="{UPSTREAM}" target="_blank" rel="noopener" class="hover:text-gray-200">BentoPDF</a> &middot;
<a href="/pdf/LICENSE.txt" class="hover:text-gray-200">AGPL-3.0</a> &middot;
<a href="/pdf/source/aaronpdf-source.tar.gz" class="hover:text-gray-200">Source archive</a> &middot;
<a href="{source_tree_url(commit)}" target="_blank" rel="noopener" class="hover:text-gray-200">Fork {short}</a></span>
</nav>
</footer>"""

EXTRA_CSS = f"""/* AaronPDF additions (rebrand.py) */
:root{{--apdf-accent:{ACCENT}}}
#nav-brand a,#footer-brand{{letter-spacing:-.02em}}
.apdf-nav .nav-link,.apdf-nav .mobile-nav-link{{white-space:nowrap}}
.apdf-footer a{{transition:color .15s}}
.apdf-footer a:hover{{color:var(--apdf-accent)}}
.apdf-credit{{margin-top:2rem;padding-top:1.25rem;border-top:1px solid rgba(255,255,255,.08);font-size:.75rem;line-height:1.6;color:#9ca3af;text-align:center}}
.apdf-credit p+p{{margin-top:.35rem}}
.apdf-credit a{{color:#d1d5db;text-decoration:underline;text-underline-offset:2px}}
.apdf-credit a:hover{{color:var(--apdf-accent)}}
.apdf-accent{{color:var(--apdf-accent)}}
.apdf-prose h2{{font-size:1.4rem;font-weight:700;color:#fff;margin:2rem 0 .75rem}}
.apdf-prose p,.apdf-prose li{{color:#d1d5db;line-height:1.7}}
.apdf-prose p{{margin:0 0 .9rem}}
.apdf-prose ul{{list-style:disc;padding-left:1.25rem}}
.apdf-prose a{{color:var(--apdf-accent);text-decoration:underline}}
.apdf-prose code{{background:#1f2937;padding:.1rem .35rem;border-radius:.25rem;font-size:.85em}}
"""

# ---------------------------------------------------------------- favicon
def monogram_svg(bg=True):
    rect = f'<rect width="64" height="64" rx="14" fill="{BG}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{rect}'
            f'<path fill="{ACCENT}" d="M27 10h10l17 44h-10.5l-3.6-10H24.1l-3.6 10H10zM27.3 35h9.4L32 21.6z"/></svg>\n')

def write_icons(pdf):
    img = pdf / "images"
    wr(img / "favicon.svg", monogram_svg(True))
    wr(img / "favicon-no-bg.svg", monogram_svg(False))
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise SystemExit("Pillow is required to draw the AaronPDF icons (pip install pillow)")
    def render(size, bg=True):
        sc = 8; S = size * sc
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        k = S / 64
        if bg: d.rounded_rectangle([0, 0, S - 1, S - 1], radius=14 * k, fill=BG)
        outer = [(27, 10), (37, 10), (54, 54), (43.5, 54), (39.9, 44), (24.1, 44), (20.5, 54), (10, 54)]
        d.polygon([(x * k, y * k) for x, y in outer], fill=ACCENT)
        hole = [(27.3, 35), (36.7, 35), (32, 21.6)]
        d.polygon([(x * k, y * k) for x, y in hole], fill=BG if bg else (0, 0, 0, 0))
        return im.resize((size, size), Image.LANCZOS)
    render(192).save(img / "favicon-192x192.png")
    render(512).save(img / "favicon-512x512.png")
    render(180).save(img / "apple-touch-icon.png")
    render(64).save(img / "favicon.png")
    render(256).save(pdf / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

# ---------------------------------------------------------------- HTML
def rebrand_text(s):
    s = s.replace("© 2026 BentoPDF. All rights reserved.", f"{BRAND}, a modified version of BentoPDF (AGPL-3.0).")
    s = s.replace("Bento PDF", BRAND)
    return s.replace("BentoPDF", BRAND)

def transform_html(path, rel, version, commit):
    s = rd(path)
    # head ------------------------------------------------------------
    s = re.sub(r'<script src="/pdf/assets/language-redirect-[^"]*"[^>]*></script>\s*', "", s)
    s = re.sub(r'<link rel="alternate" hreflang="[^"]*" href="[^"]*">', "", s)
    s = re.sub(r'\s*<meta (?:property|name)="(?:og:image[^"]*|twitter:image[^"]*|twitter:site|twitter:creator|keywords)" content="[^"]*">', "", s)
    s = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex, nofollow">', s)
    s = re.sub(r'<meta name="author" content="[^"]*">', '<meta name="author" content="Aaron Katzin (modified BentoPDF)">', s)
    url = page_url(rel)
    if rel == "index.html":
        home_title = f"{BRAND} - Private PDF tools in your browser"
        s = re.sub(r"<title>.*?</title>", f"<title>{home_title}</title>", s, count=1, flags=re.S)
        s = re.sub(r'(<meta (?:name="title"|property="og:title"|name="twitter:title") content=")[^"]*', r"\g<1>" + home_title, s)
        s = re.sub(r'(<meta (?:name="description"|property="og:description"|name="twitter:description") content=")[^"]*',
                   r"\g<1>" + TAGLINE + " Merge, split, compress, convert, sign and edit PDFs without uploading them.", s)
    s = re.sub(r'(<link rel="canonical" href=")[^"]*(")', r"\g<1>%s\2" % url, s)
    s = re.sub(r'(<meta (?:property|name)="(?:og|twitter):url" content=")[^"]*(")', r"\g<1>%s\2" % url, s)
    s = re.sub(r'<!-- (?:Twitter Card|Open Graph[^>]*|JSON-LD[^>]*) -->', "", s)
    # all JSON-LD (SEO only; includes Organization/WebSite/any rating markup)
    s = re.sub(r'\s*<script type="application/ld\+json"[^>]*>.*?</script>', "", s, flags=re.S)
    if "apdf.css" not in s:
        s = s.replace("</head>", '<link rel="stylesheet" href="/pdf/apdf.css">\n</head>', 1)
    # header nav --------------------------------------------------------
    m = re.search(r'<nav class="bg-gray-900 border-b border-white/10 sticky top-0 z-30">', s)
    if m:
        a, b = element_span(s, m.start())
        old = s[a:b]
        bm = re.search(r'<button id="mobile-menu-button"', old)
        btn = old[slice(*element_span(old, bm.start()))] if bm else ""
        s = s[:a] + nav_html(btn) + s[b:]
    # footer ------------------------------------------------------------
    fm = re.search(r"<footer\b[^>]*>", s)
    if fm:
        a, b = element_span(s, fm.start())
        compact = "flex-none" in fm.group(0)
        s = s[:a] + (compact_footer_html(commit) if compact else footer_html(version, commit)) + s[b:]
    # marketing sections ------------------------------------------------
    for marker in ['id="donation-ribbon"', 'id="security-compliance-section"', 'id="testimonials-section"',
                   'id="faq-accordion"', 'id="ads-section"']:
        s = remove_by_marker(s, marker)
    s = remove_by_marker(s, "<!-- USED BY SECTION START -->", tag="section")
    s = re.sub(r"<!-- (?:COMPLIANCE SECTION (?:START|END)|Donation Ribbon|USED BY SECTION END) -->", "", s)
    if 'id="features-section"' in s:
        s = remove_by_marker(s, 'id="features-section"', replacement='<section id="features-section" class="hidden"></section>')
    # hero copy (home page)
    s = s.replace('<span class="lp-h1-lead" data-i18n="hero.title">The</span>', '<span class="lp-h1-lead">Aaron\'s</span>')
    s = re.sub(r'<p class="lp-sub" data-i18n="compliance.processingLocal">.*?</p>',
               f'<p class="lp-sub">{TAGLINE} Your files never leave your device.</p>', s, flags=re.S)
    s = s.replace('<span data-i18n="hero.startUsing">Start Using Now</span>', '<span>Pick a tool</span>')
    # links to removed pages / disabled tools / socials ----------------
    s = tool_card_pattern().sub("", s)
    s = re.sub(r'<a\b[^>]*href="https?://(?:www\.)?%s[^"]*"[^>]*>.*?</a>' % SOCIAL_HOSTS, "", s, flags=re.S)
    # remaining in-text links to removed pages -> plain text
    s = re.sub(r'(<a\b[^>]*href="(?:https?://(?:www\.)?bentopdf\.com)?/pdf/(?:%s)(?:\.html)?(?:/[^"]*)?(?:[#?][^"]*)?"[^>]*>)(.*?)</a>'
               % "|".join(map(re.escape, REMOVED_PAGES + REMOVED_DIRS)), lambda mm: mm.group(2), s, flags=re.S)
    s = re.sub(r'(<a\b[^>]*href="https?://(?:www\.)?bentopdf\.com[^"]*"[^>]*>)(.*?)</a>', lambda mm: mm.group(2), s, flags=re.S)
    # brand strings (credit HTML is inserted already; protect it) ------
    parts = re.split(r'(<footer class="[^"]*apdf-footer.*?</footer>)', s, flags=re.S)
    s = "".join(p if i % 2 else rebrand_text(p) for i, p in enumerate(parts))
    wr(path, s)

# ---------------------------------------------------------------- About & License page
def about_page(pdf, version, commit):
    tpl = rd(pdf / "404.html")
    a = tpl.find('<div id="app"'); a, b = element_span(tpl, a)
    third = sorted(str(p.relative_to(pdf)) for p in pdf.rglob("LICENSE*") if p.is_file())
    tl = "\n".join(f'<li><a href="/pdf/{t}"><code>{t}</code></a></li>' for t in third)
    body = f"""<div id="app" class="min-h-screen container mx-auto p-4 md:p-8">
<section class="apdf-prose max-w-3xl mx-auto py-10">
<h1 class="text-4xl font-bold text-white mb-4">About <span class="apdf-accent">{BRAND}</span></h1>
<p>{BRAND} is Aaron Katzin's personal PDF toolkit. {TAGLINE} Files are processed locally with JavaScript and
WebAssembly; they are never uploaded. Some advanced tools download their processing engines (PyMuPDF, Ghostscript,
CoherentPDF, Tesseract OCR data) from the jsDelivr CDN the first time you use them. The site is served from Cloudflare.</p>
<p>Office-format converters (Word, Excel, PowerPoint, OpenDocument, RTF, Pages, Publisher, Visio, WordPerfect, WPS) are
disabled in this deployment because their LibreOffice engine is too large for this host.</p>
<h2 id="license">License</h2>
<p>{BRAND} is a <strong>modified version of <a href="{UPSTREAM}">BentoPDF</a></strong>, created by
<a href="{UPSTREAM_AUTHOR}">alam00000</a> and contributors. BentoPDF and this modified version are licensed under the
<a href="/pdf/LICENSE.txt">GNU Affero General Public License, version 3</a> (AGPL-3.0). This program is distributed in
the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the license for details. {BRAND} is not affiliated with or endorsed by BentoPDF;
the name was changed so it is not mistaken for the official BentoPDF service.</p>
<p>Modified by Aaron Katzin, {MODIFIED}. Changes: renamed to {BRAND} with a new logo; replaced header and footer;
removed marketing content (donation banner, customer logos, statistics, compliance badges, testimonials, home-page FAQ,
social links, links to the author's other products, blog, company pages, SEO landing pages and structured data);
English only (translated page sets removed); Office converters disabled; LibreOffice WASM, source maps and type
declarations removed; this About &amp; License page added.</p>
<h2 id="source">Source code</h2>
<ul>
<li>Full corresponding source for this deployment:
<a href="{source_tree_url(commit)}">AaronKatzin/bentopdf @ {commit[:12]}</a>
(a fork of BentoPDF {version}). That git tree is the complete source: upstream BentoPDF plus the
<code>aaronpdf/</code> changes. Rebuild it with <code>bash aaronpdf/build.sh</code>
(<code>BASE_URL=/pdf/</code>, then this rebrand).</li>
<li><a href="/pdf/source/aaronpdf-source.tar.gz">aaronpdf-source.tar.gz</a> &mdash; the AaronPDF scripts from that
same commit (<code>rebrand.py</code>, headers, Wrangler config, license, and the README with rebuild steps).</li>
<li>Original project: <a href="{UPSTREAM}">alam00000/bentopdf</a>.</li>
</ul>
<h2 id="third-party">Third-party software</h2>
<p>{BRAND} includes or loads third-party components under their own licenses, including PDF.js (Apache-2.0),
pdf-lib (MIT), qpdf (Apache-2.0), CoherentPDF, PyMuPDF and Ghostscript (AGPL-3.0, loaded from CDN),
Tesseract.js (Apache-2.0), Tailwind CSS and Lucide (MIT/ISC) and others. License texts shipped with this build:</p>
<ul>
{tl}
</ul>
<p>License comments inside the bundled JavaScript files are kept unchanged.</p>
</section>
</div>"""
    s = tpl[:a] + body + tpl[b:]
    s = re.sub(r"<title>.*?</title>", f"<title>About &amp; License | {BRAND}</title>", s, flags=re.S)
    s = re.sub(r'(<meta name="(?:title|description)" content=")[^"]*', r"\g<1>About and license information for %s" % BRAND, s)
    s = re.sub(r'(<meta (?:property|name)="(?:og|twitter):(?:title|description)" content=")[^"]*', r"\g<1>About %s" % BRAND, s)
    s = s.replace(page_url("404.html"), page_url("about.html"))
    wr(pdf / "about.html", s)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dest")
    default_license = Path(__file__).resolve().parent.parent / "LICENSE"
    ap.add_argument("--license", default=str(default_license))
    a = ap.parse_args()
    rebrand_site(Path(a.src), Path(a.dest), Path(a.license), resolve_commit())

def rebrand_site(src, dest, license_path, commit):
    if not license_path.is_file():
        raise SystemExit(f"AGPL license text not found: {license_path}")
    if dest.exists(): shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=False, ignore=shutil.ignore_patterns(".git"))
    pdf = dest / "pdf"
    # 1. slim
    for l in LANGS: shutil.rmtree(pdf / l, ignore_errors=True)
    shutil.rmtree(pdf / "libreoffice-wasm", ignore_errors=True)
    for p in list(pdf.rglob("*.map")) + list(pdf.rglob("*.d.ts")): p.unlink()
    for d in REMOVED_DIRS: shutil.rmtree(pdf / d, ignore_errors=True)
    for f in REMOVED_FILES + [p + ".html" for p in REMOVED_PAGES + OFFICE_TOOLS]:
        if (pdf / f).exists(): (pdf / f).unlink()
    if (pdf / ".well-known").exists() and not any((pdf / ".well-known").iterdir()):
        (pdf / ".well-known").rmdir()
    version = (re.search(r'<span id="app-version">([^<]+)</span>', rd(pdf / "index.html")) or [None, "?"])[1]
    # 2-4. HTML (about.html is upstream's personal page -> replaced below)
    if (pdf / "about.html").exists(): (pdf / "about.html").unlink()
    for p in sorted(pdf.rglob("*.html")):
        rel = str(p.relative_to(pdf))
        if rel.startswith(("pdfjs-viewer/", "pdfjs-annotation-viewer/", "docs/")): continue
        transform_html(p, rel, version, commit)
    about_page(pdf, version, commit)
    # root redirect page
    r = dest / "index.html"
    if r.exists(): wr(r, rebrand_text(rd(r)))
    # JS bundles: display strings only (capitalised brand; ids/keys/urls are lowercase 'bentopdf')
    for p in (pdf / "assets").glob("*.js"):
        s = rd(p); t = rebrand_text(s)
        if t != s: wr(p, t)
    sw = pdf / "sw.js"
    if sw.exists():   # new cache name so browsers drop cached pages from the previous deploy
        short = commit[:7] if commit and commit != "unknown" else "local"
        def _cache(m):
            base = m.group(1).split("-aaronpdf-")[0]
            return f"const CACHE_VERSION = 'bentopdf-{base}-aaronpdf-{short}';"
        wr(sw, re.sub(r"const CACHE_VERSION = 'bentopdf-([^']*)';", _cache, rd(sw)))
    # locale JSON
    for p in (pdf / "locales").rglob("*.json"):
        s = rd(p); t = rebrand_text(s)
        if t != s: wr(p, t)
    # manifest
    mf = pdf / "site.webmanifest"
    m = json.loads(rd(mf))
    m.update(name=BRAND, short_name=BRAND, description=TAGLINE, theme_color=BG, background_color=BG)
    wr(mf, json.dumps(m, indent=4) + "\n")
    # runtime config: disable Office tools (hidden from grid, search, shortcuts, workflow, direct URL)
    cfg = pdf / "config.json"
    c = json.loads(rd(cfg)) if cfg.exists() else {}
    c["disabledTools"] = sorted(set(c.get("disabledTools", []) + OFFICE_TOOLS))
    wr(cfg, json.dumps(c, indent=2) + "\n")
    wr(pdf / "apdf.css", EXTRA_CSS)
    shutil.copy(license_path, pdf / "LICENSE.txt")
    write_icons(pdf)
    print("rebranded", dest, "version", version)

if __name__ == "__main__":
    main()
