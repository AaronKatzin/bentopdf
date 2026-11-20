#!/usr/bin/env node
/**
 * Lay out the prebuilt site for a static host that cannot run npm.
 *
 * Vite's dist/ is placed in a folder matching BASE_URL (default /pdf/).
 * A root index.html redirects to that folder. serve.json is what
 * `npx serve@14 -s .` reads: -s rewrites every extensionless path to the
 * root index.html before looking for a file, so extensionless tool and
 * language URLs are redirected to the real HTML first.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildSecurityHeaders } from './generate-security-headers.mjs';

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..'
);

function arg(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || !process.argv[index + 1]) return null;
  return path.resolve(process.argv[index + 1]);
}

function publishBase() {
  const raw = (process.env.BASE_URL || '/pdf/').trim();
  const withSlash = raw.endsWith('/') ? raw : `${raw}/`;
  const base = withSlash.startsWith('/') ? withSlash : `/${withSlash}`;
  if (base === '/') {
    throw new Error(
      'assemble-dist-branch: BASE_URL must be a subdirectory such as /pdf/'
    );
  }
  const segment = base.slice(1, -1);
  if (!/^[A-Za-z0-9._-]+$/.test(segment)) {
    throw new Error(
      `assemble-dist-branch: BASE_URL must be a single path segment, got ${base}`
    );
  }
  return { base, segment };
}

function directoryIndexRedirects(distDir, base) {
  const redirects = [
    { source: base.slice(0, -1), destination: `${base}index.html` },
    { source: base, destination: `${base}index.html` },
  ];

  function walk(dir, rel) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const relChild = rel ? `${rel}/${entry.name}` : entry.name;
      const full = path.join(dir, entry.name);
      if (!entry.isDirectory()) continue;
      if (fs.existsSync(path.join(full, 'index.html'))) {
        redirects.push({
          source: `${base}${relChild}`,
          destination: `${base}${relChild}/index.html`,
        });
        redirects.push({
          source: `${base}${relChild}/`,
          destination: `${base}${relChild}/index.html`,
        });
      }
      walk(full, relChild);
    }
  }

  walk(distDir, '');
  return redirects;
}

function extensionlessRedirects(base) {
  const slug = '([A-Za-z0-9-]+)';
  return [
    {
      source: `${base}:page${slug}`,
      destination: `${base}:page.html`,
    },
    {
      source: `${base}:dir${slug}/:page${slug}`,
      destination: `${base}:dir/:page.html`,
    },
    {
      source: `${base}:dir${slug}/:mid${slug}/:page${slug}`,
      destination: `${base}:dir/:mid/:page.html`,
    },
  ];
}

function rootIndex(base) {
  const target = JSON.stringify(base);
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>BentoPDF</title>
    <link rel="canonical" href="${base}" />
    <meta http-equiv="refresh" content="0; url=${base}" />
    <script>
      location.replace(${target} + location.search + location.hash);
    </script>
  </head>
  <body>
    <p><a href="${base}">Continue to BentoPDF</a></p>
  </body>
</html>
`;
}

function rewriteHeaderPaths(staticHeaders, base) {
  const prefix = base.slice(0, -1);
  return staticHeaders
    .split('\n')
    .map((line) => {
      if (!line || line.startsWith(' ') || line.startsWith('\t')) return line;
      // `/*` already covers the publish root, including the /pdf/ tree.
      if (line === '/*') return line;
      if (line.startsWith('/')) return `${prefix}${line}`;
      return line;
    })
    .join('\n');
}

function main() {
  const { base, segment } = publishBase();
  const distDir = arg('--dist') || path.join(repoRoot, 'dist');
  const outDir = arg('--out') || path.join(repoRoot, 'dist-publish');

  if (!fs.existsSync(path.join(distDir, 'index.html'))) {
    throw new Error(`assemble-dist-branch: ${distDir} has no index.html`);
  }

  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  fs.cpSync(distDir, path.join(outDir, segment), {
    recursive: true,
    dereference: true,
  });
  fs.writeFileSync(path.join(outDir, 'index.html'), rootIndex(base));

  const headers = buildSecurityHeaders();
  const config = {
    cleanUrls: false,
    trailingSlash: false,
    directoryListing: false,
    redirects: [
      ...directoryIndexRedirects(distDir, base),
      ...extensionlessRedirects(base),
    ],
    headers: [
      {
        source: '**/*',
        headers: headers.headerPairs.map(([key, value]) => ({ key, value })),
      },
    ],
  };
  fs.writeFileSync(
    path.join(outDir, 'serve.json'),
    `${JSON.stringify(config, null, 2)}\n`
  );
  fs.writeFileSync(
    path.join(outDir, '_headers'),
    `${rewriteHeaderPaths(headers.staticHeaders, base).trimEnd()}\n`
  );

  console.log(
    `assemble-dist-branch: wrote ${outDir} (${segment}/ + root redirect, ${config.redirects.length} redirects)`
  );
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main();
}
