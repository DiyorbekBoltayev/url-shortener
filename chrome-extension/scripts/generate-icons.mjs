// Generate solid-brand-color PNG placeholders for extension icons.
//
// No dependencies: writes valid RGBA PNGs by hand using zlib.
// Run:   node scripts/generate-icons.mjs
// Output: public/icons/icon-16.png, icon-48.png, icon-128.png
//
// Replace with real branded icons before Chrome Web Store submission.

import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, '..', 'public', 'icons');

// Brand color: blue-600 (#2563eb) with a subtle inner rounded square mark.
const BRAND = [0x25, 0x63, 0xeb, 0xff];
const FG = [0xff, 0xff, 0xff, 0xff];

function crc32(buf) {
  let c;
  const table = crc32.table || (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      t[n] = c >>> 0;
    }
    return t;
  })());
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = (crc >>> 8) ^ table[(crc ^ buf[i]) & 0xff];
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function makeIcon(size) {
  // Draw a rounded-ish (approximated) brand square with a small inner "link" bar.
  const bytesPerRow = size * 4;
  const raw = Buffer.alloc((bytesPerRow + 1) * size);
  const inset = Math.max(2, Math.round(size * 0.18));
  const barThickness = Math.max(2, Math.round(size * 0.12));
  const barYTop = Math.round(size * 0.45) - Math.floor(barThickness / 2);
  const barYBot = barYTop + barThickness;
  for (let y = 0; y < size; y++) {
    raw[y * (bytesPerRow + 1)] = 0; // filter byte: None
    for (let x = 0; x < size; x++) {
      const off = y * (bytesPerRow + 1) + 1 + x * 4;
      // outer transparent corners (very rough rounded effect)
      const cornerR = Math.round(size * 0.18);
      const inTL = x < cornerR && y < cornerR && (cornerR - x) ** 2 + (cornerR - y) ** 2 > cornerR * cornerR;
      const inTR = x >= size - cornerR && y < cornerR && (x - (size - cornerR - 1)) ** 2 + (cornerR - y) ** 2 > cornerR * cornerR;
      const inBL = x < cornerR && y >= size - cornerR && (cornerR - x) ** 2 + (y - (size - cornerR - 1)) ** 2 > cornerR * cornerR;
      const inBR = x >= size - cornerR && y >= size - cornerR && (x - (size - cornerR - 1)) ** 2 + (y - (size - cornerR - 1)) ** 2 > cornerR * cornerR;
      if (inTL || inTR || inBL || inBR) {
        raw[off] = 0;
        raw[off + 1] = 0;
        raw[off + 2] = 0;
        raw[off + 3] = 0;
        continue;
      }
      // inner white link bar
      if (x >= inset && x < size - inset && y >= barYTop && y < barYBot) {
        raw[off] = FG[0];
        raw[off + 1] = FG[1];
        raw[off + 2] = FG[2];
        raw[off + 3] = FG[3];
      } else {
        raw[off] = BRAND[0];
        raw[off + 1] = BRAND[1];
        raw[off + 2] = BRAND[2];
        raw[off + 3] = BRAND[3];
      }
    }
  }

  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter
  ihdr[12] = 0; // interlace
  const idat = deflateSync(raw);
  return Buffer.concat([
    signature,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  for (const size of [16, 48, 128]) {
    const buf = makeIcon(size);
    const file = path.join(OUT_DIR, `icon-${size}.png`);
    writeFileSync(file, buf);
    console.log(`[icons] wrote ${file} (${buf.length} bytes)`);
  }
}

main();
