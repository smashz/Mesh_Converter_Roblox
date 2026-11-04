// Minimal stdio JSON-RPC client for Roblox StudioMCP.exe
// Usage: node mcp_call.js list | node mcp_call.js call <tool> <jsonArgsFile>
const { spawn } = require('child_process');
const fs = require('fs');
const exe = 'C:/Users/guara/AppData/Local/Roblox/Versions/version-7062aec9dbe74b14/StudioMCP.exe';
const p = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'] });
let buf = '', id = 0; const pending = {};
p.stdout.on('data', d => { buf += d; let i; while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!line) continue; try { const m = JSON.parse(line); if (m.id != null && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } } catch (e) {} } });
p.stderr.on('data', d => process.stderr.write(d));
const req = (method, params) => new Promise(r => { const myId = ++id; pending[myId] = r; p.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: myId, method, params }) + '\n'); });
(async () => {
  await req('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'programmer', version: '1' } });
  p.stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n');
  await new Promise(r => setTimeout(r, 6000));
  const [cmd, tool, argFile] = process.argv.slice(2);
  let res;
  if (cmd === 'list') res = await req('tools/list', {});
  else if (cmd === 'luau') res = await req('tools/call', { name: 'execute_luau', arguments: { datamodel_type: process.argv[4] || 'Edit', code: fs.readFileSync(tool, 'utf8') } });
  else res = await req('tools/call', { name: tool, arguments: argFile ? JSON.parse(fs.readFileSync(argFile, 'utf8')) : {} });
  if (res.result && res.result.content) { for (const c of res.result.content) { if (c.type === 'image') { const f = require('path').resolve(__dirname, '..', 'screens', (process.env.SHOT || 'shot') + '.png'); fs.writeFileSync(f, Buffer.from(c.data, 'base64')); console.log('saved ' + f); } else console.log(c.text || JSON.stringify(c).slice(0, 500)); } if (res.result.isError) console.log('[isError]'); } else console.log(JSON.stringify(res, null, 1));
  p.kill(); process.exit(0);
})();
setTimeout(() => { console.error('timeout'); p.kill(); process.exit(1); }, 110000);
