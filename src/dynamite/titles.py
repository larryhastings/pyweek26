import math

import pyglet.graphics
import pyglet.sprite
from pyglet.event import EVENT_HANDLED
from pyglet import clock
from pyglet import gl
from pyglet.text import Label

from . import animation
from .scene import AnchoredImg


BODY_FONT = 'Edo'


class Screen:
    SPRITES = []

    def __init__(self, window, next_screen=None):
        handlers = {}
        for k in dir(self):
            if k.startswith('on_'):
                handlers[k] = getattr(self, k)
        self.window = window
        self.next_screen = next_screen
        self.load()
        self.batch = pyglet.graphics.Batch()
        self.t = 0
        self.clock = clock.Clock(time_function=self._time)
        clock.schedule(self._tick)
        self.start()
        window.push_handlers(**handlers)

    def _time(self):
        return self.t

    def _tick(self, dt):
        self.t += dt
        self.clock.tick(True)

    def start(self):
        """Start the screen."""

    def end(self):
        self.window.pop_handlers()
        clock.unschedule(self._tick)
        if self.next_screen:
            self.next_screen(self.window)

    def load(self):
        self.imgs = {}
        self.sprites = {}
        for spr in self.SPRITES:
            if isinstance(spr, AnchoredImg):
                s = self.sprites[spr.name] = spr.load()
            else:
                s = self.sprites[spr] = pyglet.resource.image(f'{spr}.png')
                s.anchor_x = s.width // 2
                s.anchor_y = 10

    def on_draw(self):
        gl.glClearColor(66 / 255, 125 / 255, 193 / 255, 0)
        self.window.clear()
        self.batch.draw()
        return EVENT_HANDLED

    def on_key_press(self, *args):
        return EVENT_HANDLED

    def on_key_release(self, *args):
        return EVENT_HANDLED


class TitleScreen(Screen):
    SPRITES = [
        AnchoredImg('dynamite-valley'),
    ]

    def start(self):
        self.title = pyglet.sprite.Sprite(
            self.sprites['dynamite-valley'],
            x=self.window.width // 2,
            y=self.window.height // 2 + 50,
            batch=self.batch,
        )
        self.title.scale = 0.1
        self.clock.animate(
            self.title,
            'bounce_end',
            duration=2,
            scale=1.2,
            on_finished=self.show_label
        )

    def show_label(self):
        self.label = Label(
            "Press any key to begin",
            x=self.window.width // 2,
            y=200,
            font_name=BODY_FONT,
            font_size=20,
            anchor_x='center',
            anchor_y='center',
            color=(255, 255, 255, 0),
            batch=self.batch,
        )
        self.clock.schedule(self.update_label)

    def update_label(self, dt):
        opacity = 0.5 - math.cos(self.t * 4) * 0.5
        self.label.color = (
            *self.label.color[:3],
            round(opacity * 255)
        )

    def on_key_press(self, k, modifiers):
        self.end()
