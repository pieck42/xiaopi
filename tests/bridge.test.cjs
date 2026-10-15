const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {XiaopiBridgeCore, textOnly} = require('../cindy-bridge/core.js');
const {createBridge} = require('../cindy-bridge/node/server.cjs');

function fixture() {
  let saved = {}, created = 0, dispatched = 0, loseReply = false;
  const requests = new Map();
  const task = {taskId: 'test-task', revision: 1};
  const store = {load: async () => structuredClone(saved), save: async s => { saved = structuredClone(s); }};
  const tasks = {
    capabilities: async () => ({operations: ['create', 'get', 'send', 'getRun', 'readMessages']}),
    create: async () => { created++; return {...task}; },
    get: async () => ({...task}),
    send: async payload => {
      const old = requests.get(payload.requestKey);
      if (old) { assert.deepEqual(old.payload, payload); return old.run; }
      const run = {runId: 'test-run-' + ++dispatched, status: 'queued'};
      requests.set(payload.requestKey, {payload: structuredClone(payload), run});
      task.revision++;
      if (loseReply) { loseReply = false; throw Error('Simulated lost acknowledgement'); }
      return run;
    },
    getRun: async ({runId}) => ({runId, status: 'completed'}),
    readMessages: async () => ({items: [
      {id: 'm1', role: 'assistant', content: [{type: 'thinking', thinking: 'private'}, {type: 'text', text: '真实回复'}]},
      {id: 'm2', role: 'tool_result', content: 'not for display'},
    ], nextCursor: null}),
  };
  return {tasks, store, core: () => new XiaopiBridgeCore(tasks, store),
    counters: () => ({created, dispatched}), loseNext: () => { loseReply = true; }};
}

test('restart reuses task; repeated message id dispatches only once', async () => {
  const f = fixture(); let c = f.core();
  const cmd = {action: 'send', messageId: 'msg-1', text: '你好'};
  await c.command(cmd);
  c = f.core(); await c.command(cmd);
  await c.command({action: 'send', messageId: 'msg-2', text: '你记得上一句吗'});
  assert.deepEqual(f.counters(), {created: 1, dispatched: 2});
  assert.equal((await c.snapshot()).messages.length, 1);
});

test('lost send acknowledgement survives restart without new key/revision or duplicate execution', async () => {
  const f = fixture(); f.loseNext();
  await assert.rejects(f.core().command({action: 'send', messageId: 'msg-1', text: '只执行一次'}));
  const restarted = f.core();
  await assert.rejects(restarted.command({action: 'send', messageId: 'msg-2', text: 'different'}));
  await restarted.command({action: 'send', messageId: 'msg-1', text: '只执行一次'});
  assert.deepEqual(f.counters(), {created: 1, dispatched: 1});
  assert.equal((await restarted.snapshot()).pending, false);
});

test('missing/deleted bound task fails without silently making another', async () => {
  const f = fixture(), c = f.core(); await c.command({action: 'connect'});
  f.tasks.get = async () => { throw Error('NOT_FOUND'); };
  await assert.rejects(f.core().command({action: 'connect'}));
  assert.equal(f.counters().created, 1);
});

test('reconciling run blocks new input', async () => {
  const f = fixture(), c = f.core();
  await c.command({action: 'send', messageId: 'msg-1', text: 'first'});
  f.tasks.getRun = async () => ({runId: 'test-run-1', status: 'reconciling'});
  await assert.rejects(c.command({action: 'send', messageId: 'msg-2', text: 'second'}));
  assert.equal(f.counters().dispatched, 1);
});

test('text extractor does not expose reasoning or tools', () => {
  assert.equal(textOnly([{type: 'thinking', text: 'private'}, {type: 'tool_use', text: 'secret'}, {type: 'text', text: 'hello'}]), 'hello');
  assert.equal(textOnly('[{"type":"text","text":"你好"}]'), '你好');
});

test('real loopback service enforces authentication, origin, and command deduplication', async () => {
  const dir = fs.mkdtempSync(path.join(__dirname, '../.xiaopi/test-'));
  const descriptor = path.join(dir, 'bridge.json');
  const notifications = [];
  const b = createBridge({descriptorPath: descriptor, notify: v => notifications.push(v)});
  try {
    await b.start();
    const {port, token} = JSON.parse(fs.readFileSync(descriptor));
    const url = `http://127.0.0.1:${port}`;
    assert.equal((await fetch(url + '/status')).status, 403);
    const headers = {Authorization: 'Bearer ' + token};
    assert.equal((await fetch(url + '/status', {headers: {...headers, Origin: 'https://example.com'}})).status, 403);
    const badHostStatus = await new Promise((resolve, reject) => {
      const req = http.get(url + '/status', {headers: {...headers, Host: 'evil.example'}}, res => {
        res.resume(); resolve(res.statusCode);
      });
      req.on('error', reject);
    });
    assert.equal(badHostStatus, 403);
    const cmd = {id: 'command-1', action: 'connect'};
    const send = value => fetch(url + '/command', {method: 'POST', headers, body: JSON.stringify(value)});
    assert.equal((await send(cmd)).status, 202);
    assert.equal((await send(cmd)).status, 200);
    assert.equal((await send({...cmd, action: 'refresh'})).status, 409);
    assert.equal(notifications.length, 1);
    b.complete({id: cmd.id, ok: true});
    b.update({taskId: 'example', messages: []});
    const result = await (await fetch(url + '/status', {headers})).json();
    assert.equal(result.commands[0].status, 'done');
    assert.equal(result.snapshot.taskId, 'example');
  } finally {
    b.close();
    assert.equal(path.dirname(dir), path.resolve(__dirname, '../.xiaopi'));
    fs.rmSync(dir, {recursive: true, force: true});
  }
});
