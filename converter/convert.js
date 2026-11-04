// Converts the models listed in tools/converter/assets.json with headless Blender into
// build/playtest_assets/<Id>.json (+ manifest.json). Originals are only read, never modified.
// Usage: node tools/converter/convert.js [Id ...]       (no ids = all)
// Env: BLENDER = path to blender.exe (default: Blender 5.2 in Program Files)
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..', '..');
const outDir = path.join(root, 'build', 'playtest_assets');
const blender = process.env.BLENDER || 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const map = JSON.parse(fs.readFileSync(path.join(__dirname, 'assets.json'), 'utf8'));
const only = process.argv.slice(2);
const manifestPath = path.join(outDir, 'manifest.json');
fs.mkdirSync(outDir, { recursive: true });
const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};

let failed = 0;
for (const [id, entry] of Object.entries(map)) {
  if (id.startsWith('_') || (only.length && !only.includes(id))) continue;
  const args = ['-b', '--factory-startup', '--python', path.join(__dirname, 'convert_model.py'), '--',
    path.join(root, entry.source), path.join(outDir, id + '.json'), '--name', id,
    '--tex', String(entry.tex || 512), '--pose', entry.pose || 'idle', '--height', String(entry.height || 5)];
  let out = '';
  try { out = execFileSync(blender, args, { encoding: 'utf8', timeout: 300000, maxBuffer: 64 << 20 }); }
  catch (e) { out = (e.stdout || '') + (e.stderr || ''); }
  const line = out.split(/\r?\n/).find(l => l.startsWith('MBE_CONVERT '));
  if (!line) { failed++; console.log(`FAIL ${id}: ${out.split(/\r?\n/).filter(l => /Error|Exception/.test(l)).slice(-3).join(' | ')}`); continue; }
  const r = JSON.parse(line.slice(12));
  manifest[id] = { source: entry.source, height: entry.height, yaw: entry.yaw, size: r.size, pose: r.pose,
    submeshes: r.submeshes, vertices: r.vertices, triangles: r.triangles, textures: r.textures, bytes: r.bytes };
  console.log(`ok   ${id}: ${r.vertices} verts, ${r.triangles} tris, ${r.submeshes} part(s), ${(r.bytes / 1e6).toFixed(2)} MB, pose ${r.pose}`);
}
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
process.exit(failed ? 1 : 0);
