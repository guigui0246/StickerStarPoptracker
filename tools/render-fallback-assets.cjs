// Run with Node.js and sharp available (NODE_PATH may point to bundled modules).
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
async function files(dir) {
  const result = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const name = path.join(dir, entry.name);
    if (entry.isDirectory()) result.push(...await files(name));
    else result.push(name);
  }
  return result;
}
(async () => {
  const references = [];
  for (const dir of ['items', 'maps', 'locations']) {
    for (const file of await files(path.join(root, dir))) {
      if (!file.endsWith('.json')) continue;
      const original = await fs.readFile(file, 'utf8');
      JSON.parse(original);
      const updated = original.replace(/images\/[^"\s]+\.svg/g, source => {
        references.push(source);
        return source.replace(/\.svg$/, '.png');
      });
      references.push({ file, original, updated });
    }
  }
  const assets = [...new Set(references.filter(x => typeof x === 'string'))];
  for (const source of assets) {
    const target = source.replace(/\.svg$/, '.png');
    // Only rasterize referenced fallbacks; never overwrite official game icons.
    await sharp(path.join(root, source)).png().toFile(path.join(root, target));
  }
  for (const entry of references.filter(x => typeof x !== 'string')) {
    if (entry.original !== entry.updated) await fs.writeFile(entry.file, entry.updated);
  }
  console.log(`Rendered ${assets.length} fallback assets and updated their references.`);
})().catch(error => { console.error(error); process.exitCode = 1; });
