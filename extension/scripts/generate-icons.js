/**
 * Generate extension PNG icons (16, 48, 128) from assets/icon.svg.
 * Run: node scripts/generate-icons.js
 * Requires: npm install sharp --save-dev
 */

const path = require("path");
const fs = require("fs");

const sizes = [16, 48, 128];
const assetsDir = path.join(__dirname, "..", "assets");
const svgPath = path.join(assetsDir, "icon.svg");

async function main() {
  let sharp;
  try {
    sharp = require("sharp");
  } catch {
    console.error(
      "Missing 'sharp'. Install with: npm install sharp --save-dev"
    );
    process.exit(1);
  }

  if (!fs.existsSync(svgPath)) {
    console.error("Source not found: assets/icon.svg");
    process.exit(1);
  }

  const svg = fs.readFileSync(svgPath);

  for (const size of sizes) {
    const outPath = path.join(assetsDir, `icon${size}.png`);
    await sharp(svg)
      .resize(size, size)
      .png()
      .toFile(outPath);
    console.log(`Wrote ${outPath}`);
  }
  console.log("Done.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
