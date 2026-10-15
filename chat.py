"""Local text UI. Only the installed Cindy plugin can execute agent requests."""
from pathlib import Path
import json
import os
import queue
import re
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import uuid


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class BridgeClient:
    def __init__(self, descriptor=None):
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
        self.descriptor = Path(descriptor) if descriptor else base / 'Xiaopi' / 'bridge.json'
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, route, payload=None):
        try:
            connection = json.loads(self.descriptor.read_text(encoding='utf-8'))
            port, token = connection['port'], connection['token']
            if type(port) is not int or not 1024 <= port <= 65535 or not re.fullmatch(r'[0-9a-f]{64}', token):
                raise ValueError('invalid descriptor')
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError('尚未连接 Cindy：请安装并启用“小皮连接”插件，然后点“连接”。') from None
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        req = Request(f'http://127.0.0.1:{port}{route}', data=data,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=5) as response:
                body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise RuntimeError('对话内容过大，请在 Cindy 中查看。')
            return json.loads(body)
        except HTTPError as error:
            if error.code == 403:
                raise RuntimeError('连接信息已更新，请重新连接；仍失败时重新启用插件。') from None
            try:
                message = json.loads(error.read(4096)).get('error')
            except (ValueError, OSError):
                message = None
            raise RuntimeError(message or '本地连接请求失败，请稍后重试。') from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            raise RuntimeError('Cindy 连接已断开，请确认 Cindy 正在运行并启用“小皮连接”插件。') from None
        except ValueError:
            raise RuntimeError('本地连接返回格式异常，请重新启用插件。') from None

    def command(self, action, **kwargs):
        return self.request('/command', {'id': str(uuid.uuid4()), 'action': action, **kwargs})


class ChatWindow:
    def __init__(self, pet):
        self.pet = pet
        self.client = BridgeClient()
        self.events = queue.Queue()
        self.in_flight = False
        self.closed = False
        self.connected = False
        self.active_command = None
        self.last_messages = None
        self.run_status = None
        self.last_reply = None
        self.message_rows = []
        self.positioned = False
        self.outbox_path = Path(__file__).resolve().parent / '.xiaopi' / 'outbox.json'
        try:
            self.outbox = json.loads(self.outbox_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.outbox = None
        self.window = tk.Toplevel(pet.root)
        self.window.title('和小皮聊天 · Cindy')
        screen_w, screen_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        self.window.geometry(f'{min(1080, screen_w-80)}x{min(820, screen_h-120)}')
        self.window.minsize(min(700, screen_w-80), min(560, screen_h-120))
        self.window.configure(bg='#15252e')
        self.window.attributes('-topmost', pet.topmost)
        self.window.protocol('WM_DELETE_WINDOW', self.hide)
        self.window.bind('<Escape>', lambda event: self.hide())
        toolbar = tk.Frame(self.window, bg='#15252e')
        toolbar.pack(fill='x', padx=24, pady=(18, 4))
        tk.Label(toolbar, text='和小皮聊聊', fg='#e2f5e8', bg='#15252e',
                 font=('Microsoft YaHei', 22, 'bold')).pack(side='left')
        self.connect_button = tk.Button(toolbar, text='连接 Cindy', command=lambda: self.submit('connect'),
                                        font=('Microsoft YaHei', 12), padx=12, pady=5)
        self.connect_button.pack(side='right')
        self.status = tk.StringVar(value='连接 Cindy 后可开始文字交流。')
        self.status_label = tk.Label(self.window, textvariable=self.status, wraplength=960, justify='left',
                 anchor='w', fg='#b4f1cf', bg='#15252e', font=('Microsoft YaHei', 12))
        self.status_label.pack(fill='x', padx=24, pady=(2, 10))
        self.panes = tk.PanedWindow(self.window, orient='vertical', bg='#43615f',
                                   sashwidth=10, sashrelief='flat', borderwidth=0, opaqueresize=True)
        self.panes.pack(fill='both', expand=True, padx=24, pady=(0, 20))
        reply_panel = tk.Frame(self.panes, bg='#15252e')
        tk.Label(reply_panel, text='对话与回复', anchor='w', bg='#15252e', fg='#b4f1cf',
                 font=('Microsoft YaHei', 14, 'bold')).pack(fill='x', pady=(0, 8))
        self.transcript = ScrolledText(reply_panel, state='disabled', wrap='char', height=8, bg='#15252e',
                 fg='#eef7f4', relief='flat', font=('Microsoft YaHei', 4), padx=0, pady=12,
                 cursor='arrow', borderwidth=0, highlightthickness=0)
        self.transcript.pack(fill='both', expand=True)
        self.transcript.bind('<Configure>', self.resize_messages)
        composer = tk.Frame(self.panes, bg='#15252e')
        tk.Label(composer, text='在这里输入', anchor='w', fg='#e2f5e8', bg='#15252e',
                 font=('Microsoft YaHei', 15, 'bold')).pack(fill='x', pady=(10, 8))
        actions = tk.Frame(composer, bg='#15252e')
        actions.pack(side='bottom', fill='x', pady=(10, 0))
        tk.Label(actions, text='Enter 发送 · Shift+Enter 换行', bg='#15252e', fg='#bfd5d0',
                 font=('Microsoft YaHei', 11)).pack(side='left')
        self.send_button = tk.Button(actions, text='发送给小皮', command=self.send, state='disabled',
                 bg='#b4f1cf', fg='#15252e', activebackground='#d5ffe6', relief='flat',
                 font=('Microsoft YaHei', 15, 'bold'), padx=22, pady=10, cursor='hand2')
        self.send_button.pack(side='right')
        self.retry_button = tk.Button(actions, text='重试原消息', command=self.retry, state='disabled',
                 font=('Microsoft YaHei', 12), padx=10, pady=10)
        self.editor = tk.Text(composer, height=3, wrap='word', font=('Microsoft YaHei', 18),
                 bg='#f4faf7', fg='#15252e', insertbackground='#15252e', insertwidth=3,
                 padx=14, pady=12, relief='flat', highlightthickness=2,
                 highlightbackground='#7aa494', highlightcolor='#b4f1cf', undo=True)
        self.editor.pack(fill='both', expand=True)
        self.editor.bind('<Return>', self.on_enter)
        self.panes.add(reply_panel, minsize=140, stretch='always')
        self.panes.add(composer, minsize=220, stretch='never')
        self.window.bind('<Configure>', self.on_resize)
        if self.outbox:
            self.editor.insert('1.0', self.outbox.get('text', ''))
            self.status.set('有一条发送结果待确认的消息；连接后可重试原消息，不会自动重发。')
        self.poll()
        self.drain()

    def show(self):
        self.window.deiconify()
        if not self.positioned:
            self.window.update_idletasks()
            width, height = self.window.winfo_width(), self.window.winfo_height()
            x = max(0, (self.window.winfo_screenwidth()-width)//2)
            y = max(0, (self.window.winfo_screenheight()-height)//2-30)
            self.window.geometry(f'+{x}+{y}')
            self.panes.sash_place(0, 0, max(140, int(self.panes.winfo_height()*.62)))
            self.positioned = True
        self.window.lift(); self.editor.focus_set()

    def on_resize(self, event):
        if event.widget is self.window:
            self.status_label.configure(wraplength=max(300, event.width-48))

    def resize_messages(self, event=None):
        width = max(180, self.transcript.winfo_width()-28)
        for row, bubble, body in self.message_rows:
            row.configure(width=width)
            body.configure(wraplength=max(120, int(width*.8)-36))
            row.update_idletasks()
            row.configure(height=bubble.winfo_reqheight()+18)

    def scroll_messages(self, event):
        self.transcript.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def hide(self):
        self.window.withdraw()

    def on_enter(self, event):
        if event.state & 1:
            return None
        self.send()
        return 'break'

    def background(self, fn, kind):
        if self.in_flight or self.closed:
            return False
        self.in_flight = True
        def run():
            try:
                self.events.put((kind, fn()))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=run, daemon=True).start()
        return True

    def submit(self, action, **kwargs):
        if self.background(lambda: self.client.command(action, **kwargs), 'accepted'):
            self.status.set('正在连接…' if action == 'connect' else '正在提交消息…')
            self.set_buttons(False)

    def save_outbox(self):
        if self.outbox:
            self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.outbox_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.outbox, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.outbox_path)
        else:
            self.outbox_path.unlink(missing_ok=True)

    def send(self):
        if self.in_flight or self.active_command or not self.connected:
            return
        if self.outbox:
            self.status.set('请先重试原消息，确认发送结果。'); return
        if self.run_status and self.run_status not in ('completed', 'failed', 'cancelled', 'interrupted', 'rejected'):
            self.status.set('Cindy 仍在处理上一条消息，请稍候或在 Cindy 查看。'); return
        text = self.editor.get('1.0', 'end-1c').strip()
        if not text or len(text) > 16000:
            self.status.set('请输入 1–16000 字的文字。'); return
        self.outbox = {'messageId': str(uuid.uuid4()), 'text': text}
        try:
            self.save_outbox()
        except OSError:
            self.outbox = None
            self.status.set('无法保存待发送消息，请检查项目目录写权限。'); return
        self.submit('send', **self.outbox)

    def retry(self):
        if self.outbox and not self.in_flight and not self.active_command:
            self.submit('send', **self.outbox)

    def set_buttons(self, ready):
        self.connect_button.configure(state='normal' if not self.in_flight and not self.active_command else 'disabled')
        free = ready and not self.in_flight and not self.active_command
        busy_run = self.run_status and self.run_status not in ('completed', 'failed', 'cancelled', 'interrupted', 'rejected')
        self.send_button.configure(state='normal' if free and not self.outbox and not busy_run else 'disabled')
        self.retry_button.configure(state='normal' if free and self.outbox else 'disabled')
        if self.outbox:
            if not self.retry_button.winfo_manager(): self.retry_button.pack(side='right', padx=8)
        else:
            self.retry_button.pack_forget()

    def apply_status(self, result):
        view = result['snapshot']
        self.connected = bool(view.get('taskId'))
        self.run_status = (view.get('run') or {}).get('status')
        if self.outbox and view.get('lastMessageId') == self.outbox.get('messageId'):
            self.outbox = None
            self.save_outbox()
            self.editor.delete('1.0', 'end')
        if self.active_command:
            command = next((c for c in result.get('commands', []) if c['id'] == self.active_command), None)
            if command and command['status'] != 'pending':
                self.active_command = None
                if command['status'] == 'error':
                    self.status.set(command.get('error') or '请求失败，请在 Cindy 检查。')
                    self.set_buttons(self.connected)
                    self.render_messages(view.get('messages', []))
                    return
            elif command is None:
                self.active_command = None
                self.status.set('连接已重启，请确认原消息结果，必要时重试原消息。')
        if view.get('error'):
            self.status.set(view['error'])
        elif self.active_command:
            self.status.set('正在提交，请在 Cindy 完成可能出现的权限确认…')
        elif view.get('pending') or self.outbox:
            self.status.set('原消息的发送结果待确认，请点“重试原消息”；不会自动重发。')
        elif self.connected:
            labels = {'queued': '消息已排队', 'running': 'Cindy 正在处理', 'completed': '回复完成',
                      'failed': '本轮处理失败，请在 Cindy 查看', 'cancelled': '本轮已取消',
                      'reconciling': '正在核对执行状态，请勿重复发送', 'stopping': '正在停止'}
            self.status.set(labels.get(self.run_status, '已连接固定对话' if not self.run_status else '处理中：' + self.run_status))
        else:
            self.status.set('连接服务已就绪，点“连接”创建或恢复固定对话。')
        if self.run_status in ('running', 'queued', 'reconciling', 'stopping'):
            if self.pet.state != 'thinking': self.pet.set_state('thinking')
        elif self.run_status in ('failed', 'cancelled', 'interrupted', 'rejected'):
            if self.pet.state != 'idle': self.pet.set_state('idle')
        self.render_messages(view.get('messages', []))
        self.set_buttons(self.connected)

    def render_messages(self, messages):
        signature = json.dumps(messages, ensure_ascii=False)
        if signature == self.last_messages: return
        self.last_messages = signature
        at_bottom = self.transcript.yview()[1] >= .98
        old_position = self.transcript.yview()[0]
        for row, _, _ in self.message_rows:
            row.destroy()
        self.message_rows.clear()
        self.transcript.configure(state='normal'); self.transcript.delete('1.0', 'end')
        for message in messages:
            user = message['role'] == 'user'
            row = tk.Frame(self.transcript, bg='#15252e', width=700, height=90)
            row.pack_propagate(False)
            color = '#315846' if user else '#233944'
            bubble = tk.Frame(row, bg=color, padx=18, pady=12)
            bubble.pack(side='right' if user else 'left', anchor='n', pady=(0, 18))
            name = tk.Label(bubble, text='你' if user else '小皮', bg=color,
                            fg='#b4f1cf', font=('Microsoft YaHei', 12, 'bold'), anchor='w')
            name.pack(fill='x', pady=(0, 6))
            body = tk.Label(bubble, text=message['text'], bg=color, fg='#eef7f4',
                            font=('Microsoft YaHei', 18), wraplength=540, justify='left', anchor='w')
            body.pack(fill='x')
            for widget in (row, bubble, name, body):
                widget.bind('<MouseWheel>', self.scroll_messages)
            self.message_rows.append((row, bubble, body))
            self.transcript.window_create('end', window=row, align='top')
            self.transcript.insert('end', '\n')
        if not messages:
            self.transcript.tag_configure('empty', foreground='#9ab6b1', font=('Microsoft YaHei', 16), justify='center')
            self.transcript.insert('end', '\n和小皮说说今天的事吧。\n在下方输入文字，回复会显示在这里。', 'empty')
        self.transcript.configure(state='disabled')
        self.resize_messages()
        if at_bottom:
            self.transcript.see('end')
        else:
            self.transcript.yview_moveto(old_position)
        if self.run_status == 'completed' and messages:
            final = next((m for m in reversed(messages) if m['role'] == 'assistant'), None)
            if final and final['id'] != self.last_reply:
                self.last_reply = final['id']
                self.pet.set_state('speaking')
                self.pet.set_caption(final['text'][:100])

    def drain(self):
        if self.closed: return
        try:
            while True:
                kind, result = self.events.get_nowait()
                self.in_flight = False
                if kind == 'accepted':
                    self.active_command = result['id']
                elif kind == 'status':
                    try: self.apply_status(result)
                    except (OSError, ValueError, KeyError): self.status.set('无法恢复本地状态，请在 Cindy 检查会话。')
                else:
                    self.connected = False; self.active_command = None
                    self.status.set(result)
                self.set_buttons(self.connected)
        except queue.Empty:
            pass
        self.window.after(100, self.drain)

    def poll(self):
        if self.closed: return
        self.background(lambda: self.client.request('/status'), 'status')
        self.window.after(1500, self.poll)

    def close(self):
        self.closed = True
        self.window.destroy()
