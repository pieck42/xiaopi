"""Xiaopi: a local, transparent Windows desktop companion prototype."""
from pathlib import Path
import ctypes
import json
import math
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
from PIL import ImageTk
from animation import SpriteAtlas, ACTION_NAMES, MANIFEST, frame_index

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'settings.json'
KEY = '#010203'
STATES = {
    'idle': '我在这里，陪你慢慢来。',
    'listening': '嗯，我在听。（模拟）',
    'thinking': '让我想一想……（模拟）',
    'speaking': '今天也一起，做点有意思的事吧！',
    'happy': '见到你，开心加倍！',
}


class Xiaopi:
    def __init__(self):
        self.smoke_test = '--smoke-test' in sys.argv
        try:
            self.config = json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.config = {}
        self.skin = self.config.get('skin', 'dragon')
        if self.skin not in ('fox', 'dragon'):
            self.skin = 'dragon'
        self.size = int(self.config.get('size', 380))
        self.size = max(180, min(800, self.size))
        self.state = 'idle'
        self.topmost = bool(self.config.get('topmost', True))
        self.root = tk.Tk()
        self.root.title('小皮 · 桌面伙伴')
        self.root.overrideredirect(True)
        self.root.configure(bg=KEY)
        self.root.attributes('-transparentcolor', KEY)
        self.root.attributes('-topmost', self.topmost)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.atlases = {name: SpriteAtlas(name) for name in ('fox', 'dragon')}
        self.frames = {}
        self.demo_jobs = []
        self.chat = None
        self.drag = None
        self.settings_window = None
        self.started = time.monotonic()
        self.root.bind('<ButtonPress-1>', self.press)
        self.root.bind('<B1-Motion>', self.move)
        self.root.bind('<ButtonRelease-1>', self.release)
        self.root.bind('<Button-3>', self.popup)
        self.root.bind('<Double-Button-1>', self.double_click)
        self.root.bind('<Motion>', self.pointer_cursor)
        self.root.bind('<Escape>', lambda e: self.set_state('idle'))
        self.root.bind('<Control-q>', lambda e: self.close())
        self.root.bind('<Control-Return>', lambda e: self.open_chat())
        for index, state in enumerate(STATES, 1):
            self.root.bind(str(index), lambda e, s=state: self.set_state(s))
        self.layout()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, min(screen_w - self.width, int(self.config.get('x', screen_w-self.width-30))))
        y = max(0, min(screen_h - self.height - 45, int(self.config.get('y', screen_h-self.height-70))))
        self.root.geometry(f'+{x}+{y}')
        self.animate()

    def layout(self):
        self.canvas.delete('all')
        self.caption_font = tkfont.Font(root=self.root, family='Microsoft YaHei', size=max(12, self.size//21))
        self.width = self.size+60
        self.caption = self.canvas.create_text(self.width/2, 20, anchor='n',
            fill='#e2f5e8', width=self.width-40, font=self.caption_font, justify='center')
        # Measure actual canvas text, including wrapping and the current Windows DPI.
        caption_text = getattr(self, 'caption_text', STATES[self.state])
        max_bottom = 0
        for text in (*STATES.values(), caption_text):
            self.canvas.itemconfigure(self.caption, text=text)
            max_bottom = max(max_bottom, self.canvas.bbox(self.caption)[3])
        self.canvas.itemconfigure(self.caption, text=caption_text)
        self.bubble_box = (5, 5, self.width-5, max_bottom+16)
        self.bubble = self.canvas.create_rectangle(*self.bubble_box,
            fill='#15252e', outline='#43615f', width=2)
        self.canvas.tag_lower(self.bubble)
        self.sprite_center_y = self.bubble_box[3]+24+self.size/2
        self.sprite = self.canvas.create_image(self.width/2, self.sprite_center_y)
        self.height = int(self.sprite_center_y+self.size/2+78)
        self.chat_button_box = (18, self.height-57, self.width-18, self.height-9)
        self.canvas.create_rectangle(*self.chat_button_box, fill='#b4f1cf', outline='#d5ffe6', width=2)
        self.canvas.create_text((self.chat_button_box[0]+self.chat_button_box[2])/2, self.height-33,
            text='和小皮聊天  ›', fill='#15252e', font=('Microsoft YaHei', max(12, self.size//25), 'bold'))
        self.root.geometry(f'{self.width}x{self.height}')
        self.frames.clear()

    def clamp_position(self):
        self.root.update_idletasks()
        x = max(0, min(self.root.winfo_x(), self.root.winfo_screenwidth()-self.width))
        y = max(0, min(self.root.winfo_y(), self.root.winfo_screenheight()-self.height-45))
        self.root.geometry(f'+{x}+{y}')

    def set_caption(self, text):
        self.caption_text = text
        self.layout()
        self.draw_sprite(0)
        self.clamp_position()

    def animate(self):
        t = time.monotonic()-self.started
        self.draw_sprite(frame_index(self.state, t*1000))
        dy = -2*math.sin(t*math.tau/3) if self.state == 'idle' else 0
        if self.state == 'happy':
            dy = -14*abs(math.sin(t*math.pi/.6))
        self.canvas.coords(self.sprite, self.width/2, self.sprite_center_y+dy)
        self.root.after(60, self.animate)

    def draw_sprite(self, index):
        key = (self.skin, self.state, index)
        if key not in self.frames:
            self.frames[key] = ImageTk.PhotoImage(self.atlases[self.skin].render(self.state, index, self.size))
        self.canvas.itemconfigure(self.sprite, image=self.frames[key])

    def save(self):
        if self.smoke_test:
            return
        self.config.update(skin=self.skin, size=self.size, topmost=self.topmost,
                           x=self.root.winfo_x(), y=self.root.winfo_y())
        CONFIG.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')

    def switch(self, name=None):
        self.skin = name or ('fox' if self.skin == 'dragon' else 'dragon')
        self.started = time.monotonic()
        self.draw_sprite(0)
        self.save()

    def set_state(self, name, cancel=True):
        if cancel:
            self.cancel_demo()
        self.state = name
        self.started = time.monotonic()
        self.set_caption(STATES[name])

    def cancel_demo(self):
        for job in self.demo_jobs:
            self.root.after_cancel(job)
        self.demo_jobs.clear()

    def demo(self):
        self.cancel_demo()
        self.set_state('idle', cancel=False)
        for ms, state in ((3300,'listening'), (6100,'thinking'), (9100,'speaking'), (11900,'happy'), (14900,'idle')):
            self.demo_jobs.append(self.root.after(ms, lambda s=state: self.set_state(s, cancel=False)))

    def resize(self, size, persist=True):
        self.size = max(180, min(800, int(size)))
        self.layout()
        self.draw_sprite(0)
        self.clamp_position()
        if persist:
            self.save()

    def pointer_cursor(self, event):
        self.canvas.configure(cursor='hand2' if self.over_chat_button(event) else '')

    def over_chat_button(self, event):
        left, top, right, bottom = self.chat_button_box
        return left <= event.x <= right and top <= event.y <= bottom

    def double_click(self, event):
        if not self.over_chat_button(event):
            self.switch()

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = self.settings_window = tk.Toplevel(self.root)
        window.title('小皮设置')
        window.resizable(False, False)
        window.attributes('-topmost', self.topmost)
        frame = tk.Frame(window, padx=24, pady=20)
        frame.pack()
        tk.Label(frame, text='形象大小', font=('Microsoft YaHei', 13)).pack(anchor='w')
        self.settings_size = tk.IntVar(value=self.size)
        self.settings_value = tk.StringVar(value=f'{round(self.size/380*100)}%')
        tk.Label(frame, textvariable=self.settings_value, font=('Microsoft YaHei', 11)).pack(anchor='e')
        self.size_slider = tk.Scale(frame, from_=180, to=800, orient='horizontal',
            length=320, resolution=1, showvalue=False, variable=self.settings_size,
            command=self.update_size_setting)
        self.size_slider.pack(fill='x', pady=(0, 16))
        tk.Button(frame, text='完成', command=self.close_settings,
            font=('Microsoft YaHei', 11), padx=18).pack(anchor='e')
        window.protocol('WM_DELETE_WINDOW', self.close_settings)
        window.update_idletasks()
        x = max(0, min(self.root.winfo_x(), window.winfo_screenwidth()-window.winfo_width()))
        y = max(0, min(self.root.winfo_y(), window.winfo_screenheight()-window.winfo_height()-45))
        window.geometry(f'+{x}+{y}')
        window.lift()

    def update_size_setting(self, value):
        size = int(float(value))
        if size != self.size:
            self.resize(size, persist=False)
        self.settings_value.set(f'{round(self.size/380*100)}%')

    def close_settings(self):
        if self.settings_window is not None:
            self.save()
            self.settings_window.destroy()
            self.settings_window = None

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes('-topmost', self.topmost)
        self.save()

    def popup(self, event):
        menu = tk.Menu(self.root, tearoff=False, font=('Microsoft YaHei', 12))
        menu.add_command(label='和小皮聊天…', command=self.open_chat)
        menu.add_separator()
        for key, label in (('fox','小狐狸'), ('dragon','小龙')):
            menu.add_command(label=('✓ ' if self.skin == key else '   ')+label, command=lambda k=key:self.switch(k))
        menu.add_separator()
        for key, label in (('idle','待机'),('listening','倾听'),('thinking','思考'),('speaking','回答'),('happy','开心')):
            menu.add_command(label=ACTION_NAMES[key]+'（模拟）', command=lambda k=key:self.set_state(k))
        menu.add_command(label='播放完整互动演示', command=self.demo)
        menu.add_command(label='设置…', command=self.open_settings)
        menu.add_command(label=('✓ ' if self.topmost else '')+'保持在最上层', command=self.toggle_topmost)
        menu.add_separator()
        menu.add_command(label='退出小皮', command=self.close)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def press(self, event):
        if self.over_chat_button(event):
            self.drag = None
            self.open_chat()
            return
        self.drag = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.moved = False

    def move(self, event):
        if self.drag:
            mx, my, x, y = self.drag
            dx, dy = event.x_root-mx, event.y_root-my
            if abs(dx)+abs(dy)>5:
                self.moved = True
            x = max(0, min(self.root.winfo_screenwidth()-self.width, x+dx))
            y = max(0, min(self.root.winfo_screenheight()-self.height-45, y+dy))
            self.root.geometry(f'+{x}+{y}')

    def release(self, event):
        if self.drag:
            if not self.moved:
                self.set_state('happy')
                self.demo_jobs.append(self.root.after(1800, lambda:self.set_state('idle', cancel=False)))
            self.save()
        self.drag = None

    def close(self):
        self.close_settings()
        if self.chat:
            self.chat.close()
        self.save()
        self.root.destroy()

    def open_chat(self):
        if self.chat is None:
            from chat import ChatWindow
            self.chat = ChatWindow(self)
        self.chat.show()


if __name__ == '__main__':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    # One desktop pet per workspace. A second launch does not create a duplicate.
    if '--smoke-test' not in sys.argv:
        ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\XiaopiDesktopPrototype')
        if ctypes.windll.kernel32.GetLastError() == 183:
            sys.exit(0)
    app = Xiaopi()
    if '--smoke-test' in sys.argv:
        app.root.withdraw()
        def check():
            import hashlib
            try:
                for skin in ('fox','dragon'):
                    app.switch(skin)
                    signatures = set()
                    for state in STATES:
                        app.set_state(state)
                        poses = []
                        for index in (0, 1):
                            app.draw_sprite(index)
                            rendered = app.atlases[skin].render(state, index, 280)
                            box = rendered.getchannel('A').getbbox()
                            assert box and box[0] > 0 and box[1] > 0 and box[2] < 280 and box[3] < 280, (skin,state,index,'clipped')
                            poses.append(hashlib.sha256(rendered.tobytes()).hexdigest())
                        assert poses[0] != poses[1], (skin,state,'duplicate frames')
                        signatures.add(poses[0])
                        first, second = MANIFEST['timings'][state]
                        assert frame_index(state,0) == 0
                        assert frame_index(state,first) == 1
                        assert frame_index(state,first+second) == 0
                    assert len(signatures) == 5, (skin,'duplicate states')
                app.resize(380)
                app.resize(280)
                app.set_state('idle')
                print('PASS: 20 distinct frames, 10 state animations, alpha bounds, loop timings and desktop rendering')
                app.close()
            except Exception:
                app.root.destroy()
                raise
        def failed_callback(*args):
            import traceback
            traceback.print_exception(*args)
            sys.exit(1)
        app.root.report_callback_exception = failed_callback
        app.root.after(500, check)
    elif '--demo' in sys.argv:
        app.root.after(800, app.demo)
    elif '--chat' in sys.argv:
        app.root.after(300, app.open_chat)
    app.root.mainloop()
