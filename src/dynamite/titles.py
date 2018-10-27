import math

import pyglet.graphics
import pyglet.sprite
from pyglet.event import EVENT_HANDLED
from pyglet import clock
from pyglet import gl
from pyglet.text import Label
import pyglet.window.key as key

from . import animation
from .scene import AnchoredImg


BODY_FONT = 'Edo'

serial_number = 0

current_screen = None

class Screen:
    SPRITES = []
    BGCOLOR = 66 / 255, 125 / 255, 193 / 255
    ended = False

    def log(self, *a):
        s = " ".join(str(s) for s in a)
        # print(f"\n[{self.__class__.__name__}] #{self.serial_number} {s}\n")

    def __init__(self, window, on_finished=None):
        global current_screen
        if current_screen:
            current_screen.end()
        current_screen = self

        handlers = {}
        global serial_number
        serial_number += 1
        self.serial_number = serial_number
        self.log("__init__.  large and in charge.")
        for k in dir(self):
            if k.startswith('on_'):
                handlers[k] = getattr(self, k)
        self.window = window
        self.on_finished = on_finished
        self.load()
        self.batch = pyglet.graphics.Batch()
        self.t = 0

        self.clock = clock.Clock(time_function=self._time)
        clock.schedule(self._tick)
        self.start()
        self.log(">>>> push handlers >>>>")
        window.push_handlers(**handlers)

    def _time(self):
        return self.t

    def _tick(self, dt):
        self.t += dt
        self.clock.tick(True)

    def start(self):
        """Start the screen."""

    def end(self):
        if self.ended:
            return
        self.ended = True
        global current_screen
        current_screen = None
        self.log("<<<< pop handlers <<<<")
        self.window.pop_handlers()
        clock.unschedule(self._tick)
        self.log(f"end() smaller, and no longer in charge.  finished handler is {self.on_finished}.")
        if self.on_finished:
            self.on_finished()

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
        gl.glClearColor(*self.BGCOLOR, 0)
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
        'valley-art',
    ]

    def start(self):
        valley = self.sprites['valley-art']
        valley.anchor_x = valley.anchor_y = 0
        self.bg = pyglet.sprite.Sprite(
            valley,
            group=pyglet.graphics.OrderedGroup(-1),
            batch=self.batch,
        )
        self.clock.animate(
            self.bg,
            'decelerate',
            duration=15,
            y=self.window.height - valley.height,
            on_finished=self.show_label
        )
        self.clock.schedule_once(self.show_title, 12)

    def show_title(self, dt):
        self.title = pyglet.sprite.Sprite(
            self.sprites['dynamite-valley'],
            x=self.window.width // 2,
            y=self.window.height - 200,
            batch=self.batch,
            group=pyglet.graphics.OrderedGroup(1),
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
            y=100,
            font_name=BODY_FONT,
            font_size=20,
            anchor_x='center',
            anchor_y='center',
            color=(255, 255, 255, 0),
            batch=self.batch,
            group=pyglet.graphics.OrderedGroup(1),
        )
        self.clock.schedule(self.update_label)

    def update_label(self, dt):
        opacity = 0.5 - math.cos(self.t * 4) * 0.5
        self.label.color = (
            *self.label.color[:3],
            round(opacity * 255)
        )

    def on_key_press(self, k, modifiers):
        self.log(f"on_key_press {k} {modifiers}")
        self.end()


class IntroScreen(Screen):
    SPRITES = [
        AnchoredImg('dynamite-valley'),
        AnchoredImg('big-go-bomb', anchor_y=0),
    ]

    BGCOLOR = 0xaa / 255, 0x99 / 255, 0x82 / 255

    def __init__(self, window, map, on_finished=None):
        self.map = map
        super().__init__(window, on_finished=on_finished)

    def start(self):
        self.title = pyglet.sprite.Sprite(
            self.sprites['dynamite-valley'],
            x=self.window.width // 2 - 100,
            y=self.window.height - 80,
            batch=self.batch,
        )
        self.bomb = pyglet.sprite.Sprite(
            self.sprites['big-go-bomb'],
            x=self.window.width - 130,
            y=self.window.height + 100,
            batch=self.batch,
        )
        self.title.scale_x = 0.3
        self.title.scale_y = 0.5
        self.clock.animate(
            self.title,
            'bounce_end',
            duration=0.5,
            scale_x=0.9,
            scale_y=0.9,
        )
        self.clock.animate(
            self.bomb,
            'accelerate',
            duration=0.5,
            y=50,
            on_finished=self.bounce_bomb,
        )

    HIGHLIGHT_TEXT = 0x51, 0x3a, 0x1b, 255

    def bounce_bomb(self):
        self.bomb.scale_x = 1.5
        self.bomb.scale_y = 0.5
        self.clock.animate(
            self.bomb,
            'bounce_end',
            duration=0.5,
            scale_x=1,
            scale_y=1,
        )

        self.title_label = Label(
            self.map.metadata.get('title', self.map.name),
            x=self.window.width // 2,
            y=self.window.height - 200,
            font_name=BODY_FONT,
            font_size=30,
            anchor_x='center',
            anchor_y='center',
            color=(0, 0, 0, 255),
            batch=self.batch,
        )
        self.hint_label = Label(
            self.map.metadata.get('hint', 'Destroy all the beaver dams!'),
            x=self.window.width // 2,
            y=self.window.height - 300,
            font_name=BODY_FONT,
            font_size=20,
            anchor_x='center',
            anchor_y='center',
            color=self.HIGHLIGHT_TEXT,
            batch=self.batch,
        )
        self.author_label = Label(
            'Created by ' + self.map.metadata.get('author', 'Larry & Dan'),
            x=20,
            y=20,
            font_name=BODY_FONT,
            font_size=20,
            color=self.HIGHLIGHT_TEXT,
            batch=self.batch,
        )

    def on_key_press(self, k, modifiers):
        self.log(f"on_key_press {k} {modifiers}")
        self.end()

    def on_mouse_press(self, *args):
        # TODO: only when you click the bomb
        self.end()



class BackStoryScreen(Screen):
    SPRITES = [
        AnchoredImg('speech1', anchor_x=444, anchor_y=0),
        AnchoredImg('speech2', anchor_x=0, anchor_y=0),
        AnchoredImg('speech3', anchor_x=444, anchor_y=0),
    ]

    BGCOLOR = 0, 0, 0

    def start(self):
        self.bubble = 0
        self.bubbles = [
            pyglet.sprite.Sprite(
                self.sprites['speech1'],
                x=self.window.width - 50,
                y=self.window.height - 260,
                batch=self.batch,
            ),
            pyglet.sprite.Sprite(
                self.sprites['speech2'],
                x=30,
                y=self.window.height - 410,
                batch=self.batch,
            ),
            pyglet.sprite.Sprite(
                self.sprites['speech3'],
                x=self.window.width - 20,
                y=self.window.height - 540,
                batch=self.batch,
            ),
        ]
        for b in self.bubbles:
            b.visible = False

        self.clock.schedule_once(self.next_bubble, 0.5)

    def next_bubble(self, dt):
        try:
            bubble = self.bubbles[self.bubble]
        except IndexError:
            return self.end()
        self.bubble += 1

        bubble.visible = True
        bubble.scale = 0.2
        self.clock.animate(
            bubble,
            'bounce_end',
            duration=0.5,
            scale=1,
            on_finished=lambda: self.clock.schedule_once(self.next_bubble, 3)
        )

    def on_key_press(self, *_):
        self.clock.unschedule(self.next_bubble)
        self.next_bubble(0)

class GameWonScreen(Screen):
    SPRITES = [
        AnchoredImg('dynamite-valley'),
    ]

    BGCOLOR = 0xaa / 255, 0x99 / 255, 0x82 / 255

    def __init__(self, window, on_finished=None):
        super().__init__(window, on_finished=on_finished)

    def start(self):
        self.title = pyglet.sprite.Sprite(
            self.sprites['dynamite-valley'],
            x=self.window.width // 2 - 100,
            y=self.window.height - 80,
            batch=self.batch,
        )
        self.title.scale_x = 0.3
        self.title.scale_y = 0.5
        self.clock.animate(
            self.title,
            'bounce_end',
            duration=0.5,
            scale_x=0.9,
            scale_y=0.9,
        )

        self.you_won_label = Label(
            "YOU WIN!",
            x=self.window.width // 2,
            y=self.window.height - 200,
            font_name=BODY_FONT,
            font_size=30,
            anchor_x='center',
            anchor_y='center',
            color=(0, 0, 0, 255),
            batch=self.batch,
        )

        self.any_key_label = Label(
            "Press any key to continue",
            x=self.window.width // 2,
            y=100,
            font_name=BODY_FONT,
            font_size=20,
            anchor_x='center',
            anchor_y='center',
            color=(255, 255, 255, 0),
            batch=self.batch,
            group=pyglet.graphics.OrderedGroup(1),
        )

    HIGHLIGHT_TEXT = 0x51, 0x3a, 0x1b, 255


    def on_key_press(self, k, modifiers):
        self.log(f"on_key_press {k} {modifiers}")
        if k == key.SPACE:
            self.end()

    def on_mouse_press(self, *args):
        # TODO: only when you click the bomb
        self.end()
