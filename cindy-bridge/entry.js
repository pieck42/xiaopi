const core = new XiaopiBridgeCore(cindy.tasks, {
  load: async () => (await fetch('/kv')).json(),
  save: async value => {
    const response = await fetch('/kv', {method: 'PUT', body: JSON.stringify(value)});
    if (!response.ok) throw new Error('无法保存会话绑定，请在 Cindy 检查插件。');
  },
});
let chain = Promise.resolve();
const serial = fn => (chain = chain.then(fn, fn));
async function node(method, params = {}) {
  const result = await cindy.node.request({method, params});
  if (!result.ok) throw new Error(result.message || '小皮本地连接未启动。');
  return result.result;
}
async function publish() { await node('snapshot', await core.snapshot()); }
async function handle(command) {
  try {
    await core.command(command); await publish();
    await node('complete', {id: command.id, ok: true});
  } catch (error) {
    core.view.error = String(error.message || error);
    await publish();
    await node('complete', {id: command.id, ok: false,
      error: String(error.message || error), code: error.code || 'BRIDGE_ERROR'});
  }
}
cindy.onHostMessage(msg => {
  if (msg.type === 'event' && msg.name === 'node-notification' && msg.method === 'desktop-command') {
    serial(() => handle(msg.params)).catch(() => {});
  }
  if (msg.type === 'tool-call' && msg.tool === 'bridge_status') {
    serial(async () => {
      try {
        await node('start');
        await cindy.send({type: 'tool-result', callId: msg.callId, ok: true,
          result: {connected: true, taskBound: !!core.state.taskId,
            note: '桌面小皮可通过右键菜单打开聊天窗口。'}});
      } catch {
        await cindy.send({type: 'tool-result', callId: msg.callId, ok: false,
          message: '连接未启动，请重新启用小皮连接插件。'});
      }
    });
  }
});
serial(async () => { await core.load(); await node('start'); await publish(); }).catch(() => {});
let tickPending = false;
setInterval(() => {
  if (tickPending) return;
  tickPending = true;
  serial(async () => {
    await node('start');
    if (core.state.taskId) await core.refresh();
    await publish();
  }).catch(async error => {
    try { await node('snapshot', {...await core.snapshot(), error: String(error.message || error)}); } catch {}
  }).finally(() => { tickPending = false; });
}, 2000);
