const {createBridge} = require('./server.cjs');
const path = require('node:path');
const os = require('node:os');
const readline = require('node:readline');
  const descriptorPath = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), '.local', 'share'), 'Xiaopi', 'bridge.json');
  const notify = value => process.stdout.write(JSON.stringify(value) + '\n');
  const bridge = createBridge({descriptorPath, notify});
  readline.createInterface({input: process.stdin}).on('line', async line => {
    let request;
    try {
      request = JSON.parse(line);
      let result;
      switch (request.method) {
        case 'start': result = await bridge.start(); break;
        case 'snapshot': result = bridge.update(request.params); break;
        case 'complete': result = bridge.complete(request.params); break;
        default: throw new Error('未知操作。');
      }
      notify({jsonrpc: '2.0', id: request.id, result});
    } catch {
      notify({jsonrpc: '2.0', id: request?.id ?? null, error: {code: -32603, message: '小皮连接失败，请重新启用插件。'}});
    }
  }).on('close', () => { bridge.close(); process.exit(0); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { bridge.close(); process.exit(0); });
