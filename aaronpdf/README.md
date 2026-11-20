# AaronPDF

AaronPDF (https://aaronkatzin.com/pdf/) is Aaron Katzin's deployment of [BentoPDF](https://github.com/alam00000/bentopdf). BentoPDF and this fork are licensed under the **GNU Affero General Public License v3.0** — see [`LICENSE`](../LICENSE) at the repository root. AaronPDF is not affiliated with or endorsed by BentoPDF.

The live site is the static build of this repository, base path `/pdf/`, after `aaronpdf/rebrand.py` prunes and rebrands it. Cloudflare serves that directory from the Worker named `bentopdf`.

## Make a change

1. Branch from `main` and edit the application source (pages, tools, styles) the same way you would in BentoPDF.
2. Preview locally (below).
3. Open a pull request. The **Deploy AaronPDF** workflow builds the site and runs the smoke check. It does not deploy from a pull request. A failing check means the branch would not produce a deployable site.
4. Merge the pull request into `main`. That push builds the same way and runs `wrangler deploy`, which updates https://aaronkatzin.com/pdf/.

Branding, the footer, the About page, and the list of removed pages live in `aaronpdf/rebrand.py`. Security headers live in `aaronpdf/_headers`. Removed-page redirects live in `aaronpdf/_redirects`. The Worker name, account, and routes live in `aaronpdf/wrangler.jsonc`.

`rebrand.py` is applied to a fresh build every time. It is not re-run on its own output. Change the script, then rebuild.

## Preview locally

From the repository root, with Node 22 and Python 3:

```sh
npm ci
python3 -m pip install pillow
bash aaronpdf/build.sh
python3 aaronpdf/tools/serve.py aaronpdf/site 8080
```

Open http://127.0.0.1:8080/pdf/ . The preview server reads `_headers` and `_redirects` and follows the same trailing-slash and `404.html` rules as the Worker (`html_handling: auto-trailing-slash`, `not_found_handling: 404-page`).

`aaronpdf/build.sh` does four things:

1. `npm run build` with `BASE_URL=/pdf/` and `COMPRESSION_MODE=o` (one copy of each asset, no extra gzip/brotli twins). This is the same build the fork's `dist` branch publisher uses.
2. `node scripts/assemble-dist-branch.mjs`, which nests the Vite output under `pdf/` and writes a root redirect to `/pdf/`.
3. `aaronpdf/prepare_site.py`, which prunes, rebrands, copies `_headers` and `_redirects`, and writes `/pdf/source/aaronpdf-source.tar.gz`.
4. `aaronpdf/smoke.py`, which fails if the brand leaked, a file is over 25 MiB, or the license/source archive is missing.

Pillow is required. Without it the amber "A" favicon PNGs would be left as the upstream icons, so the build refuses to continue.

## What the rebrand changes

- Display name BentoPDF becomes AaronPDF (titles, visible UI strings, locale JSON, web manifest). URLs, storage keys, and code identifiers stay lowercase `bentopdf`.
- Header and footer on every page. The footer states that AaronPDF is a modified version of BentoPDF, links the AGPL text (`/pdf/LICENSE.txt`), the source archive, this fork at the deployed commit, and the original project.
- Removes the donation banner, "used by" logos, marketing stats, compliance badges, testimonials, home-page FAQ, JSON-LD, social links, GitHub star counter, links to upstream's other products, blog, company pages, and SEO hub pages.
- English only: translated `pdf/<lang>/` trees are deleted, the language auto-redirect script is removed, and the language switcher is not rendered.
- Deletes `pdf/libreoffice-wasm` (its files are over Cloudflare's 25 MiB per-asset limit) and disables the 13 Office-to-PDF tools in `pdf/config.json`. Source maps and `.d.ts` files are deleted.
- Adds `/pdf/about` and the amber "A" icon set. The service worker cache name includes the commit so a deploy is not stuck behind an old cache.

`/pdf` redirects to `/pdf/` because of `html_handling: auto-trailing-slash` (`pdf/index.html` is a directory index). That redirect is not a line in `_redirects`. `_redirects` sends removed pages such as `/pdf/kura` and `/pdf/blog` to `/pdf/` or `/pdf/about`.

## How deploy works

Workflow: [`.github/workflows/deploy-aaronpdf.yml`](../.github/workflows/deploy-aaronpdf.yml).

| Event | What runs |
| --- | --- |
| Pull request | Install, build, rebrand, smoke check, `wrangler deploy --dry-run` |
| Push to `main` | The same, then `wrangler deploy`, then `curl` https://aaronkatzin.com/pdf/ and https://aaronkatzin.com/pdf/merge-pdf for HTTP 200 |
| Actions tab, "Run workflow" | Same as a push, for the branch you select. Running it on a branch other than `main` deploys that branch to the live site. |

Wrangler is pinned to 4.165.0 and invoked with `--no-autoconfig`, so it does not try to treat the Vite app as the Worker. The config is assets-only (no Worker script):

- name `bentopdf`
- account `d94dfc30c600b4f8879e0b33387a7568`
- compatibility date `2026-11-01` (the date already on the live Worker)
- `workers_dev: true` (leave this on; setting routes would otherwise turn the workers.dev hostname off)
- assets directory `aaronpdf/site`
- `html_handling: auto-trailing-slash`
- `not_found_handling: 404-page` (a missing `/pdf/...` URL is `pdf/404.html`)
- routes `aaronkatzin.com/pdf` and `aaronkatzin.com/pdf/*` on zone `aaronkatzin.com`

`_headers` and `_redirects` sit at the top of the assets directory. Wrangler uploads them as asset configuration, not as downloadable files. The header file sets `X-Robots-Tag: noindex, nofollow`, the Content-Security-Policy, COOP/COEP, and a one-year cache on `/pdf/assets/*`.

A push to `main` also still runs **Publish static site** (`.github/workflows/publish-dist.yml`). That job force-pushes an *unmodified* build to the `dist` branch. It does not update aaronkatzin.com. The Cloudflare workflow is what updates the live site.

### Required secret

In the GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**.

| Name | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | API token created below |

The account id is already in `aaronpdf/wrangler.jsonc`. You do not need a `CLOUDFLARE_ACCOUNT_ID` secret unless you want to override that file. Wrangler reads `CLOUDFLARE_API_TOKEN` from the environment. Do not commit the token or paste it into a pull request.

### Token permissions

Create the token in the Cloudflare dashboard: **My Profile → API Tokens → Create Token → Edit Cloudflare Workers**. Scope it to this account only, and to the zone `aaronkatzin.com` only.

That template grants the permissions Wrangler asks for. The ones this deploy actually uses are:

| Scope | Permission | Why |
| --- | --- | --- |
| Account | Account Settings / Read | Wrangler confirms the account |
| Account | Workers Scripts / Edit | Upload the assets and publish Worker `bentopdf` |
| User | User Details / Read | Wrangler identifies the token |
| Zone `aaronkatzin.com` | Workers Routes / Edit | Attach `aaronkatzin.com/pdf` and `aaronkatzin.com/pdf/*` |

The template also includes Workers KV Storage / Edit, Workers Tail / Read, Workers R2 Storage / Edit, and D1 / Edit. This site does not use those. Leave them if you use the template as-is, or drop them on a custom token.

If a deploy fails looking up the zone, add **Zone / Zone / Read** on `aaronkatzin.com`. `zone_name` routes need the token to see that zone.

After the secret exists, merge to `main` or run **Deploy AaronPDF** from the Actions tab on `main`. The first successful run replaces the manually uploaded assets with the CI build.

## AGPL

The program offers its corresponding source on every page:

- `/pdf/LICENSE.txt` is the AGPL-3.0 license (the repository `LICENSE` file, unmodified).
- `/pdf/source/aaronpdf-source.tar.gz` is this `aaronpdf/` directory plus `LICENSE` and a `BUILD.txt` that records the commit. It is regenerated on every build. It never contains API tokens.
- The footer links https://github.com/AaronKatzin/bentopdf/tree/`<commit>` for that deploy. That git tree is the complete source: BentoPDF plus these modifications. `/pdf/about` repeats the same links.

Keep the `LICENSE` file and those footer links when you change the rebrand.

## Sync with upstream

This fork tracks https://github.com/alam00000/bentopdf.

```sh
git remote add upstream https://github.com/alam00000/bentopdf.git
git fetch upstream
git checkout main
git merge upstream/main
```

Resolve conflicts in application code. Prefer keeping this fork's copies of:

- `.github/workflows/deploy-aaronpdf.yml`
- `.github/workflows/publish-dist.yml`
- `aaronpdf/`
- the `if: github.repository == 'alam00000/bentopdf'` guards on upstream workflows (see below)

After a merge, run `bash aaronpdf/build.sh`. If upstream changes the Content-Security-Policy (a new CDN host, for example), `prepare_site.py` fails and names the missing source. Add that source to `aaronpdf/_headers`, keep `X-Robots-Tag` and the `/pdf/assets/*` cache rule, and rebuild. If `rebrand.py` no longer finds a header or footer it expects, the smoke check fails on a visible "BentoPDF" or a missing title; update the markers in `rebrand.py`.

Vendor tarballs under `vendor/` are normal git blobs. `npm ci` is enough; Git LFS is not required.

## Workflows that do not run on this fork

These upstream workflows are already skipped here. Each job has `if: github.repository == 'alam00000/bentopdf'`, so a push or pull request on `AaronKatzin/bentopdf` does not build Docker images, deploy GitHub Pages, open sponsor PRs, or fail for a missing upstream secret:

- `build-and-publish.yml` — Docker images to GHCR and Docker Hub, and GitHub Releases
- `static.yml` — GitHub Pages
- `sponsors.yml` — weekly sponsor README pull request
- `docker-downloads-badge.yml` — Docker download-count badge
- `update-bentopdf-viewer.yml` — scheduled engine/viewer bump
- `cla.yml` — upstream Contributor License Agreement bot
- `seo-audit.yml` — upstream SEO audit
- `tests.yml` — upstream unit tests
- `codeql.yml` — CodeQL
- `trivy-scan.yml` — image vulnerability scan

Do not remove those `if:` guards when merging upstream. This fork's own checks are **Deploy AaronPDF** and **Publish static site**.
