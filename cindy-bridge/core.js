/* Portable adapter: Cindy is the source of truth for tasks and messages. */
(function (root) {
  const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'rejected']);
  function textOnly(value) {
    if (typeof value === 'string') {
      try { const parsed = JSON.parse(value); if (typeof parsed === 'object') return textOnly(parsed); } catch {}
      return value;
    }
    if (Array.isArray(value)) return value.map(textOnly).filter(Boolean).join('\n');
    if (!value || typeof value !== 'object') return '';
    if (value.type && !['text', 'output_text', 'input_text'].includes(value.type)) return '';
    return typeof value.text === 'string' ? value.text : textOnly(value.content);
  }
  class XiaopiBridgeCore {
    constructor(tasks, store) {
      this.tasks = tasks; this.store = store; this.state = {}; this.loaded = false;
      this.view = {taskId: null, run: null, messages: [], error: null};
    }
    async load() {
      if (!this.loaded) { this.state = await this.store.load(); this.loaded = true; }
    }
    async persist() { await this.store.save(this.state); }
    async connect() {
      await this.load();
      const caps = await this.tasks.capabilities();
      for (const op of ['create', 'get', 'send', 'getRun', 'readMessages']) {
        if (!caps.operations?.includes(op)) throw new Error('当前 Cindy 不支持所需任务接口：' + op);
      }
      if (!this.state.taskId) {
        const task = await this.tasks.create({requestKey: 'xiaopi-primary-v1', title: '小皮 · 日常对话', isolatedWorkspace: true});
        if (!task.taskId) throw new Error('Cindy 未返回会话编号，未发送消息。');
        this.state.taskId = task.taskId; await this.persist();
      }
      await this.refresh();
    }
    async dispatchPending() {
      const pending = this.state.pending;
      if (!pending) return;
      // Retry the complete saved payload; never change the key or revision.
      const run = await this.tasks.send(pending.payload);
      if (!run.runId) throw new Error('发送结果不确定，请检查 Cindy，或重试同一条消息。');
      this.state.runId = run.runId;
      this.state.lastMessageId = pending.id;
      delete this.state.pending;
      await this.persist();
    }
    async send(command) {
      await this.connect();
      if (this.state.pending) {
        if (this.state.pending.id !== command.messageId) throw new Error('上一条发送结果待确认，请先重试原消息。');
        await this.dispatchPending(); return this.refresh();
      }
      if (this.state.lastMessageId === command.messageId) return this.refresh();
      if (this.view.run && !TERMINAL.has(this.view.run.status)) throw new Error('上一条消息仍在处理，请稍候或在 Cindy 查看。');
      const text = String(command.text || '').trim();
      if (!text || text.length > 16000) throw new Error('请输入 1–16000 字的文字。');
      if (!/^[a-zA-Z0-9-]{1,80}$/.test(command.messageId || '')) throw new Error('消息编号无效。');
      const task = await this.tasks.get({taskId: this.state.taskId});
      this.state.pending = {id: command.messageId, payload: {
        taskId: this.state.taskId, expectedRevision: task.revision,
        requestKey: 'xiaopi-send-' + command.messageId, text,
      }};
      await this.persist(); await this.dispatchPending(); await this.refresh();
    }
    async refresh() {
      if (!this.state.taskId) return;
      await this.tasks.get({taskId: this.state.taskId});
      this.view.taskId = this.state.taskId;
      if (this.state.runId) this.view.run = await this.tasks.getRun({runId: this.state.runId});
      let after; const messages = [];
      for (let pageNo = 0; pageNo < 20; pageNo++) {
        const page = await this.tasks.readMessages({taskId: this.state.taskId, limit: 100, ...(after ? {after} : {})});
        for (const item of page.items || []) {
          if (!['user', 'assistant'].includes(item.role)) continue;
          const text = textOnly(item.content);
          if (text) messages.push({id: item.id, role: item.role, text});
        }
        if (!page.nextCursor || page.nextCursor === after) break;
        if (pageNo === 19) throw new Error('对话历史已超过当前原型读取上限，请在 Cindy 中继续查看。');
        after = page.nextCursor;
      }
      this.view.messages = messages.slice(-120); this.view.error = null;
    }
    async command(command) {
      await this.load();
      switch (command.action) {
        case 'connect': return this.connect();
        case 'send': return this.send(command);
        case 'refresh': return this.refresh();
        case 'retry':
          if (!this.state.pending) return this.refresh();
          await this.dispatchPending(); return this.refresh();
        default: throw new Error('不支持的桌面请求。');
      }
    }
    async snapshot() {
      return {...this.view, pending: !!this.state.pending,
        pendingMessageId: this.state.pending?.id || null,
        lastMessageId: this.state.lastMessageId || null};
    }
  }
  root.XiaopiBridgeCore = XiaopiBridgeCore;
  if (typeof module !== 'undefined') module.exports = {XiaopiBridgeCore, textOnly};
})(globalThis);
