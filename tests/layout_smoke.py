"""Check the actual Tk canvas text bounds at several font/DPI scales."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv.append('--smoke-test')
from xiaopi import Xiaopi, STATES

app = Xiaopi()
app.root.withdraw()
original_scaling = app.root.tk.call('tk', 'scaling')
count = 0


def check_bounds():
    caption = app.canvas.bbox(app.caption)
    bubble = app.bubble_box
    assert bubble[0] < caption[0] < caption[2] < bubble[2], ('caption width', caption, bubble)
    assert bubble[1] < caption[1] < caption[3] < bubble[3], ('caption height', caption, bubble)
    assert bubble[3] < app.sprite_center_y-app.size/2-14, 'jump overlaps speech bubble'
    assert app.sprite_center_y+app.size/2 < app.height, 'sprite clipped at bottom'
    text_items = [item for item in app.canvas.find_all() if app.canvas.type(item) == 'text']
    assert [app.canvas.itemcget(item, 'text') for item in text_items] == [app.canvas.itemcget(app.caption, 'text'), '和小皮聊天  ›']
    assert not app.canvas.find_withtag('resize_grip'), 'desktop resize handle must stay hidden'
    for box in (caption,):
        assert 0 <= box[0] < box[2] <= app.width, ('horizontal clipping', box, app.width)
        assert 0 <= box[1] < box[3] <= app.height, ('vertical clipping', box, app.height)


try:
    for scaling in (1.0, 1.5, 2.0, 3.0):
        app.root.tk.call('tk', 'scaling', scaling)
        for size in (200, 280, 380):
            app.resize(size)
            for state in STATES:
                app.set_state(state)
                check_bounds()
                count += 1
            app.set_caption('这是一段较长的聊天回复，用来检查文字换行后，对话框会自动增加高度。'*3)
            check_bounds()
            count += 1
    print(f'PASS: {count} measured text layouts across 4 font scales and 3 pet sizes')
    from types import SimpleNamespace
    from unittest.mock import patch
    app.root.tk.call('tk', 'scaling', original_scaling)
    app.resize(380)
    app.set_state('idle')
    def corner_event(dx=0, dy=0):
        return SimpleNamespace(x=app.width-18, y=app.height-15, x_root=1000+dx, y_root=1000+dy)
    with patch.object(app, 'save') as saved:
        app.press(corner_event())
        app.move(corner_event(170, 170))
        app.release(corner_event(170, 170))
        assert app.size == 380, 'dragging desktop must not resize the pet'
        app.open_settings()
        first_window = app.settings_window
        app.open_settings()
        assert app.settings_window is first_window, 'reuse the settings window'
        app.settings_window.update()
        for value in (550, 180, 800):
            app.size_slider.set(value)
            app.root.update()
            assert app.size == value, ('settings slider', app.size, value)
        check_bounds()
        saved.reset_mock()
        app.close_settings()
        assert saved.call_count == 1 and app.settings_window is None
    print('PASS: no resize handle, desktop drag keeps size, settings slider and persistence')
finally:
    app.root.tk.call('tk', 'scaling', original_scaling)
    app.root.destroy()
