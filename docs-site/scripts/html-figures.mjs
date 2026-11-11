// Copies the images that raw HTML in docs/ references into public/, at the
// path where the page's relative URL resolves.
//
// The plan's figures are <picture> elements (a light and a dark PNG), so
// GitHub shows the one that matches the reader's theme. docs-kit copies an
// image shown with Markdown, ![alt](figure.png), but leaves raw HTML as
// written. On the site, the page docs/benchmarks/optimal-speed.md is served
// at <base>benchmarks/optimal-speed/, so its src="img/x.png" resolves to
// <base>benchmarks/optimal-speed/img/x.png: this copies the file there.
// Runs before dev and build (package.json's predev and prebuild), and
// `docs-kit check` then confirms every src resolves.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DOCS = path.join(SITE, '..', 'docs');
const PUBLIC = path.join(SITE, 'public');
// The list of copies, so a rerun removes stale ones (gitignored, not served).
const LIST = path.join(SITE, '.html-figures.json');

// The route docs-kit gives a document (see pageOf in docs-kit's sync.mjs).
function slug(rel) {
  if (rel === 'README.md') return 'overview';
  const dir = path.posix.dirname(rel);
  const base = path.posix.basename(rel, path.posix.extname(rel));
  const segs = (base === 'README' ? dir : path.posix.join(dir, base)).split('/').filter((s) => s && s !== '.');
  return segs.map((s) => s.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '')).join('/');
}

function* docs(dir, rel = '') {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) yield* docs(path.join(dir, e.name), r);
    else if (/\.mdx?$/.test(e.name)) yield r;
  }
}

const listFile = LIST;
if (fs.existsSync(listFile)) {
  for (const f of JSON.parse(fs.readFileSync(listFile, 'utf8'))) fs.rmSync(path.join(PUBLIC, f), { force: true });
}

const copies = [];
const errors = [];
for (const rel of docs(DOCS)) {
  const text = fs.readFileSync(path.join(DOCS, rel), 'utf8');
  for (const m of text.matchAll(/<(?:img|source)\b[^>]*>/g)) {
    for (const a of m[0].matchAll(/\b(src|srcset)="([^"]+)"/g)) {
      for (const url of a[2].split(',').map((s) => s.trim().split(/\s+/)[0])) {
        if (/^[a-z][a-z0-9+.-]*:|^\/|^#/i.test(url)) continue;
        const src = path.resolve(DOCS, path.dirname(rel), url);
        if (!fs.existsSync(src)) {
          const line = text.slice(0, m.index).split('\n').length;
          errors.push(`docs/${rel}:${line}: ${url} does not exist`);
          continue;
        }
        const out = path.posix.join(slug(rel), url);
        fs.mkdirSync(path.dirname(path.join(PUBLIC, out)), { recursive: true });
        fs.copyFileSync(src, path.join(PUBLIC, out));
        copies.push(out);
      }
    }
  }
}
if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
fs.writeFileSync(listFile, JSON.stringify([...new Set(copies)].sort(), null, 2) + '\n');
console.log(`html-figures: ${new Set(copies).size} images referenced by raw HTML copied into public/`);
