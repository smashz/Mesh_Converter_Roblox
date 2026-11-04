// Pushes src/ into the open Studio place through StudioMCP (Rojo-style naming:
// *.server.lua -> Script, *.client.lua -> LocalScript, *.lua -> ModuleScript, folders -> Folder).
// Usage: node tools/push.js
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const project = JSON.parse(fs.readFileSync(path.join(root, 'default.project.json'), 'utf8'));
const files = [];
const mappedRoots = [];

function walk(dir, instPath) {
  for (const name of fs.readdirSync(dir).sort()) {
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) { walk(full, instPath.concat(name)); continue; }
    if (!name.endsWith('.lua') && !name.endsWith('.luau')) continue;
    let base = name.replace(/\.luau?$/, ''), cls = 'ModuleScript';
    if (base.endsWith('.server')) { cls = 'Script'; base = base.slice(0, -7); }
    else if (base.endsWith('.client')) { cls = 'LocalScript'; base = base.slice(0, -7); }
    files.push({ instPath: instPath.concat(base), cls, source: fs.readFileSync(full, 'utf8') });
  }
}
function visit(node, instPath) {
  for (const [key, child] of Object.entries(node)) {
    if (key.startsWith('$') || typeof child !== 'object') continue;
    if (child.$path) { mappedRoots.push(instPath.concat(key).join('/')); } if (child.$path) walk(path.join(root, child.$path), instPath.concat(key));
    else visit(child, instPath.concat(key));
  }
}
visit(project.tree, []);

function longString(s) {
  let eq = '';
  while (s.includes(']' + eq + ']')) eq += '=';
  return '[' + eq + '[\n' + s + ']' + eq + ']';
}

// Folder roots are recreated so files deleted on disk disappear in Studio too.
const roots = new Set(mappedRoots);
let code = 'local function svc(n) return game:GetService(n) end\n';
code += 'local function resolve(parts, create)\n  local cur = svc(parts[1])\n  for i = 2, #parts do\n    local nxt = cur:FindFirstChild(parts[i])\n    if not nxt then if not create then return nil end nxt = Instance.new("Folder") nxt.Name = parts[i] nxt.Parent = cur end\n    cur = nxt\n  end\n  return cur\nend\n';
for (const r of roots) code += `do local f = resolve(${JSON.stringify(r.split('/')).replace(/^\[/, '{').replace(/\]$/, '}')}, false) if f then f:Destroy() end end\n`;
code += 'local n = 0\n';
for (const f of files) {
  const parent = JSON.stringify(f.instPath.slice(0, -1)).replace(/^\[/, '{').replace(/\]$/, '}');
  code += `do local s = Instance.new("${f.cls}") s.Name = ${JSON.stringify(f.instPath[f.instPath.length - 1])} s.Source = ${longString(f.source)} s.Parent = resolve(${parent}, true) n += 1 end\n`;
}
code += 'return "pushed " .. n .. " scripts"\n';
const tmp = path.join(require('os').tmpdir(), 'mbe_push.lua');
fs.writeFileSync(tmp, code);
process.stdout.write(execFileSync('node', [path.join(__dirname, 'mcp_call.js'), 'luau', tmp, 'Edit'], { encoding: 'utf8', timeout: 110000 }));
