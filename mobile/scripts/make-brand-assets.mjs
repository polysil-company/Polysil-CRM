/**
 * APP-010 · Builds every logo asset from the one logo the backend prints on quotation PDFs
 * (`backend/worker/templates/assets/polysil-logo.png`):
 * - the web app's full logo and leaf mark (`Frontend/src/assets/brand/`), favicon and Apple icon;
 * - the Android launcher icons (legacy, round and adaptive foreground) and splash screens.
 *
 * Run from the repo root once Frontend's packages are installed (it borrows Frontend's sharp):
 *   node mobile/scripts/make-brand-assets.mjs [path/to/logo.png]
 * Swap in a larger logo when the client sends one, and run it again: every size is redrawn.
 */
import { createRequire } from "node:module";
import { copyFileSync, mkdirSync, readdirSync, rmSync, existsSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..", "..");
const require = createRequire(path.join(root, "Frontend", "package.json"));
const sharp = require("sharp");

const source = path.resolve(process.argv[2] ?? path.join(root, "backend/worker/templates/assets/polysil-logo.png"));
const res = path.join(root, "mobile/android/app/src/main/res");
const brand = path.join(root, "Frontend/src/assets/brand");
const app = path.join(root, "Frontend/src/app");
const WHITE = { r: 255, g: 255, b: 255, alpha: 1 };
const CLEAR = { r: 0, g: 0, b: 0, alpha: 0 };

/** The bounding box of the leaf: everything left of the first fully empty column. */
async function markBox() {
  const { data, info } = await sharp(source).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const ink = (x, y) => {
    const i = (y * info.width + x) * 4;
    return data[i + 3] > 40 && !(data[i] > 235 && data[i + 1] > 235 && data[i + 2] > 235);
  };
  let x0 = info.width, x1 = 0, y0 = info.height, y1 = 0;
  let started = false;
  for (let x = 0; x < info.width; x++) {
    let column = 0;
    for (let y = 0; y < info.height; y++) {
      if (ink(x, y)) {
        column++;
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
      }
    }
    if (column > 0) started = true;
    else if (started) break;
  }
  return { left: x0, top: y0, width: x1 - x0 + 1, height: y1 - y0 + 1 };
}

/** The mark (or the whole logo), scaled to fit `width`×`height`, centred on a canvas. */
async function placed(input, canvas, width, height, background, radius = 0, circle = false) {
  const art = await sharp(input)
    .resize({ width, height, fit: "inside", kernel: "lanczos3" })
    .sharpen({ sigma: 0.5 })
    .png()
    .toBuffer();
  const meta = await sharp(art).metadata();
  let base = sharp({ create: { width: canvas.w, height: canvas.h, channels: 4, background: CLEAR } });
  const layers = [];
  if (background !== CLEAR) {
    const shape = circle
      ? `<svg width="${canvas.w}" height="${canvas.h}"><circle cx="${canvas.w / 2}" cy="${canvas.h / 2}" r="${canvas.w / 2}" fill="#fff"/></svg>`
      : `<svg width="${canvas.w}" height="${canvas.h}"><rect width="${canvas.w}" height="${canvas.h}" rx="${radius}" fill="#fff"/></svg>`;
    layers.push({ input: Buffer.from(shape) });
  }
  layers.push({
    input: art,
    left: Math.round((canvas.w - meta.width) / 2),
    top: Math.round((canvas.h - meta.height) / 2),
  });
  return base.composite(layers).png({ compressionLevel: 9 });
}

const box = await markBox();
const mark = await sharp(source).extract(box).png().toBuffer();
console.log("mark", box);

// Web. The logo's white wave line is transparent, so on a dark screen it shows the page
// through: both pieces sit on white, as on the PDF, and read the same in light and dark mode.
mkdirSync(brand, { recursive: true });
const logoMeta = await sharp(source).metadata();
await (await placed(source, { w: logoMeta.width + 32, h: logoMeta.height + 24 }, logoMeta.width, logoMeta.height, WHITE, 16))
  .toFile(path.join(brand, "polysil-logo.png"));
await (await placed(mark, { w: 128, h: 128 }, 100, 100, WHITE, 24)).toFile(path.join(brand, "polysil-mark.png"));
await (await placed(mark, { w: 96, h: 96 }, 76, 76, WHITE, 18)).toFile(path.join(app, "icon.png"));
await (await placed(mark, { w: 180, h: 180 }, 150, 150, WHITE)).toFile(path.join(app, "apple-icon.png"));
if (existsSync(path.join(app, "icon.svg"))) rmSync(path.join(app, "icon.svg"));

// Android launcher icons, per density.
const densities = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
for (const [name, scale] of Object.entries(densities)) {
  const dir = path.join(res, `mipmap-${name}`);
  const legacy = Math.round(48 * scale);
  const fore = Math.round(108 * scale);
  // Adaptive: the leaf inside the 66 dp safe circle (56 dp wide keeps its corners in).
  await (await placed(mark, { w: fore, h: fore }, Math.round(56 * scale), Math.round(56 * scale), CLEAR))
    .toFile(path.join(dir, "ic_launcher_foreground.png"));
  await (await placed(mark, { w: legacy, h: legacy }, Math.round(legacy * 0.78), Math.round(legacy * 0.78), WHITE, Math.round(legacy * 0.18)))
    .toFile(path.join(dir, "ic_launcher.png"));
  await (await placed(mark, { w: legacy, h: legacy }, Math.round(legacy * 0.7), Math.round(legacy * 0.7), WHITE, 0, true))
    .toFile(path.join(dir, "ic_launcher_round.png"));
}

// Splash screens: the full logo on white, half the short side wide.
for (const dir of readdirSync(res).filter((d) => d.startsWith("drawable"))) {
  const file = path.join(res, dir, "splash.png");
  if (!existsSync(file)) continue;
  const { width, height } = await sharp(file).metadata();
  const logoWidth = Math.round(Math.min(width, height) * 0.6);
  const out = await placed(source, { w: width, h: height }, logoWidth, Math.round(height * 0.3), WHITE);
  await out.flatten({ background: "#ffffff" }).toFile(file + ".tmp");
  copyFileSync(file + ".tmp", file);
  rmSync(file + ".tmp");
}
// BrandMark and BrandLogo give these sizes to <Image>: update them in brand-mark.tsx if they change.
for (const file of ["polysil-mark.png", "polysil-logo.png"]) {
  const { width, height } = await sharp(path.join(brand, file)).metadata();
  console.log(`${file}: ${width}×${height} (keep brand-mark.tsx in step)`);
}
console.log("done");
