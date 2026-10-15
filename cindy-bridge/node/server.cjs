const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const readline = require('node:readline');

function createBridge({descriptorPath, notify}) {
  const token = crypto.randomBytes(32).toString('hex');
  const commands = new Map();
  let snapshot = {taskId: null, run: null, messages: [], error: null};
  let server, starting;
  function json(res, status, value) {
    res.writeHead(status, {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'});
    res.end(JSON.stringify(value));
  }
  async function start() {
    if (starting) return starting;
    starting = new Promise((resolve, reject) => {
      server = http.createServer((req, res) => {
        const supplied = req.headers.authorization || '', wanted = 'Bearer ' + token;
        if (req.headers.host !== `127.0.0.1:${server.address().port}` || req.headers.origin ||
            Buffer.byteLength(supplied) !== Buffer.byteLength(wanted) ||
            !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(wanted))) {
          json(res, 403, {error: '连接校验失败，请重新连接小皮。'}); return;
        }
        if (req.method === 'GET' && req.url === '/status') {
          json(res, 200, {snapshot, commands: [...commands.values()]}); return;
        }
        if (req.method !== 'POST' || req.url !== '/command') { json(res, 404, {error: '未知请求。'}); return; }
        let body = '';
        req.on('data', chunk => { body += chunk; if (Buffer.byteLength(body) > 80000) req.destroy(); });
        req.on('end', () => {
          let cmd;
          try { cmd = JSON.parse(body); } catch { json(res, 400, {error: '请求格式无效。'}); return; }
          if (!/^[a-zA-Z0-9-]{1,80}$/.test(cmd.id || '') ||
              !['connect', 'send', 'refresh', 'retry'].includes(cmd.action) ||
              (cmd.action === 'send' && (typeof cmd.text !== 'string' || !cmd.text.trim() || cmd.text.length > 16000))) {
            json(res, 400, {error: '消息格式无效或过长。'}); return;
          }
          const digest = crypto.createHash('sha256').update(JSON.stringify(cmd)).digest('hex');
          const old = commands.get(cmd.id);
          if (old) {
            json(res, old.digest === digest ? 200 : 409,
              old.digest === digest ? {id: cmd.id, status: old.status} : {error: '消息编号与内容不一致。'}); return;
          }
          if ([...commands.values()].some(c => c.status === 'pending')) { json(res, 409, {error: '上一条请求仍在处理。'}); return; }
          if (commands.size >= 200) commands.delete(commands.keys().next().value);
          commands.set(cmd.id, {id: cmd.id, digest, status: 'pending', startedAt: Date.now()});
          notify({jsonrpc: '2.0', method: 'desktop-command', params: cmd});
          json(res, 202, {id: cmd.id, status: 'pending'});
        });
      });
      server.requestTimeout = 10000;
      server.on('error', reject);
      server.listen(0, '127.0.0.1', () => {
        try {
          fs.mkdirSync(path.dirname(descriptorPath), {recursive: true, mode: 0o700});
          const temp = descriptorPath + '.' + process.pid + '.tmp';
          fs.writeFileSync(temp, JSON.stringify({port: server.address().port, token, pid: process.pid}), {mode: 0o600});
          fs.renameSync(temp, descriptorPath);
          resolve({ready: true});
        } catch (e) { server.close(); reject(e); }
      });
    });
    return starting;
  }
  return {
    start,
    update(value) { snapshot = value; return {ok: true}; },
    complete(value) {
      const cmd = commands.get(value.id);
      if (cmd) Object.assign(cmd, {status: value.ok ? 'done' : 'error', error: value.error || null, code: value.code || null});
      return {ok: true};
    },
    close() {
      try { if (JSON.parse(fs.readFileSync(descriptorPath, 'utf8')).token === token) fs.unlinkSync(descriptorPath); } catch {}
      if (server) server.close();
    },
  };
}
module.exports = {createBridge};
