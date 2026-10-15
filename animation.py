"""Load and play the two generated sprite sheets without changing the source art."""
from pathlib import Path
import json
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / 'assets' / 'animations.json').read_text(encoding='utf-8'))
ACTION_NAMES = {
    'idle': '待机 · 眨眼休息',
    'listening': '倾听 · 侧耳靠近',
    'thinking': '思考 · 托腮抬眼',
    'speaking': '回答 · 张嘴示意',
    'happy': '开心 · 眯眼挥手',
}


def frame_index(state, elapsed_ms):
    first, second = MANIFEST['timings'][state]
    return int(elapsed_ms % (first + second) >= first)


class SpriteAtlas:
    def __init__(self, skin):
        self.meta = MANIFEST['skins'][skin]
        self.source = Image.open(ROOT / 'assets' / self.meta['file']).convert('RGBA')
        self.sprites = {}
        for state, frames in self.meta['frames'].items():
            for index, info in enumerate(frames):
                # A few generated frames overlap adjacent cells horizontally.
                # Select their connected alpha island so neighboring ears/tails never leak in.
                box = info['box']
                sprite = self.source.crop(box)
                alpha = sprite.getchannel('A')
                island = alpha.point(lambda a: 255 if a > 40 else 0)
                seed = (info['seed'][0]-box[0], info['seed'][1]-box[1])
                ImageDraw.floodfill(island, seed, 128)
                island = island.point(lambda a: 255 if a == 128 else 0)
                island = island.filter(ImageFilter.MaxFilter(3))
                sprite.putalpha(ImageChops.multiply(alpha, island))
                self.sprites[state, index] = sprite

    def render(self, state, index, size):
        """Common scale, centered body and stable ground line for both animation frames."""
        sprite = self.sprites[state, index]
        ratio = size * .88 / self.meta['extent']
        sprite = sprite.resize((max(1, round(sprite.width*ratio)), max(1, round(sprite.height*ratio))), Image.Resampling.NEAREST)
        frame = Image.new('RGBA', (size, size))
        frame.alpha_composite(sprite, ((size-sprite.width)//2, round(size*.94)-sprite.height))
        return frame
