"""Exercise the real Tk text window against a fake local connection (no model calls)."""
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv.append('--smoke-test')
import chat
from xiaopi import Xiaopi


class FakeClient:
    def __init__(self):
        self.sent = []
        self.view = {'taskId': 'test-task', 'run': None, 'messages': [], 'lastMessageId': None}

    def request(self, route):
        return {'snapshot': self.view, 'commands': []}

    def command(self, action, **kwargs):
        self.sent.append((action, kwargs))
        return {'id': 'test-command', 'status': 'pending'}


with patch.object(chat, 'BridgeClient', FakeClient):
    pet = Xiaopi()
    pet.root.withdraw()
    pet.open_chat()
    window = pet.chat
    window.window.withdraw()
    try:
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.xiaopi') as directory:
            window.outbox_path = Path(directory) / 'outbox.json'
            window.outbox = None
            # The worker thread has no Tk calls; apply its result on the main thread.
            window.in_flight = False
            window.apply_status(window.client.request('/status'))
            window.editor.insert('1.0', '小皮你好')
            window.send()
            record = json.loads(window.outbox_path.read_text(encoding='utf-8'))
            assert record['text'] == '小皮你好'
            message_id = record['messageId']
            window.in_flight = False
            window.active_command = None
            window.retry()
            assert window.outbox['messageId'] == message_id
            window.client.view.update(lastMessageId=message_id,
                run={'status': 'completed'},
                messages=[{'id': 'user-1', 'role': 'user', 'text': '小皮你好'},
                          {'id': 'reply-1', 'role': 'assistant', 'text': '你好，我是小皮。'}])
            window.apply_status(window.client.request('/status'))
            assert window.outbox is None and not window.outbox_path.exists()
            assert window.message_rows[0][2].cget('text') == '小皮你好'
            assert window.message_rows[1][2].cget('text') == '你好，我是小皮。'
            window.show()
            window.window.update_idletasks()
            window.resize_messages()
            window.window.update_idletasks()
            assert window.message_rows[0][1].pack_info()['side'] == 'right'
            assert window.message_rows[1][1].pack_info()['side'] == 'left'
            assert all(int(row.cget('height')) >= bubble.winfo_reqheight() for row, bubble, _ in window.message_rows)
            assert pet.state == 'speaking'
            assert window.editor.get('1.0', 'end-1c') == ''
            window.hide(); window.show(); window.window.withdraw()
        print('PASS: text window, durable message id, retry, reply rendering and pet state')
    finally:
        pet.close()
