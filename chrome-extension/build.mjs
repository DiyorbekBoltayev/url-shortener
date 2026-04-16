// Post-tsc build step:
//   1. (optional) clean dist/
//   2. copy manifest.json + public/ assets into dist/
//   3. copy non-TS sibling files (popup.html/css, options.html/css, offscreen.html)
//      so dist/ is a ready-to-load unpacked extension.
//
// Usage:
//   node build.mjs            # copy assets (run after tsc)
//   node build.mjs --clean    # remove dist/ and exit

import { cp, rm, mkdir, readdir, stat, rename } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname;
const SRC = path.join(ROOT, 'src');
const DIST = path.join(ROOT, 'dist');
const DIST_SRC = path.join(DIST, 'src');

const args = new Set(process.argv.slice(2));

async function clean() {
  if (existsSync(DIST)) {
    await rm(DIST, { recursive: true, force: true });
    console.log('[build] removed dist/');
  }
}

async function ensureDir(p) {
  await mkdir(p, { recursive: true });
}

async function copyPath(src, dest) {
  await ensureDir(path.dirname(dest));
  await cp(src, dest, { recursive: true });
}

async function copyStaticFromSrc(dir) {
  const abs = path.join(SRC, dir);
  if (!existsSync(abs)) return;
  const entries = await readdir(abs);
  for (const entry of entries) {
    const srcPath = path.join(abs, entry);
    const s = await stat(srcPath);
    if (s.isFile() && !entry.endsWith('.ts')) {
      const destPath = path.join(DIST_SRC, dir, entry);
      await copyPath(srcPath, destPath);
    }
  }
}

async function moveTscOutputUnderSrc() {
  // tsc emits into dist/ with rootDir=src, flattening the "src/" segment.
  // The manifest references paths like "src/popup/popup.js", so re-nest
  // the emitted JS under dist/src/.
  await ensureDir(DIST_SRC);
  for (const dir of ['popup', 'options', 'background', 'offscreen', 'lib']) {
    const from = path.join(DIST, dir);
    if (!existsSync(from)) continue;
    const to = path.join(DIST_SRC, dir);
    if (existsSync(to)) await rm(to, { recursive: true, force: true });
    await rename(from, to);
  }
}

async function main() {
  if (args.has('--clean')) {
    await clean();
    return;
  }

  await ensureDir(DIST);

  // Move tsc's flattened output into dist/src/ so it matches manifest paths.
  await moveTscOutputUnderSrc();

  // manifest.json
  await copyPath(path.join(ROOT, 'manifest.json'), path.join(DIST, 'manifest.json'));

  // public/ (icons + _locales)
  if (existsSync(path.join(ROOT, 'public'))) {
    await copyPath(path.join(ROOT, 'public'), path.join(DIST, 'public'));
  }

  // HTML + CSS sibling files that live alongside .ts entry points.
  await copyStaticFromSrc('popup');
  await copyStaticFromSrc('options');
  await copyStaticFromSrc('offscreen');

  console.log('[build] dist/ ready. Load it at chrome://extensions (Developer mode > Load unpacked).');
}

main().catch((err) => {
  console.error('[build] failed:', err);
  process.exitCode = 1;
});
