#!/usr/bin/env python3
import sys
import time
import datetime
import itertools
import random
from enum import Enum
from pathlib import Path

from pyglet import gl
import pyglet.image
import pyglet.window.key as key
import pyglet.window.key
import pyglet.resource

from dynamite import coords
from dynamite.coords import map_to_screen
from dynamite.particles import FlowParticles

timed_bomb_interval = 3
exploding_bomb_interval = 1/10

logic_interval = 1/120

typematic_interval = 1/4
typematic_delay = 1

# please ensure all the other intervals
# are evenly divisible into this interval
callback_interval = 1/20


player_movement_logics = typematic_interval / logic_interval


srcdir = Path(__file__).parent
pyglet.resource.path = [
    'images',
]
pyglet.resource.reindex()


FlowParticles.load()

def load_sprite(name):
    """Load a sprite and set the anchor position."""
    pc = pyglet.resource.image(name)
    pc.anchor_x = pc.width // 2
    pc.anchor_y = pc.height // 2
    return pyglet.sprite.Sprite(pc)


def load_pc(name):
    """Load a PC sprite and set the anchor position."""
    pc = pyglet.resource.image(name)
    pc.anchor_x = pc.width // 2
    pc.anchor_y = 10
    return pyglet.sprite.Sprite(pc)


def load_tile(name):
    """Load a ground tile and set the anchor position."""
    img = pyglet.resource.image(name)
    img.anchor_x = img.width // 2
    img.anchor_y = img.height // 2
    return img



remapped_keys = {
    key.W: key.UP,
    key.A: key.LEFT,
    key.S: key.DOWN,
    key.D: key.RIGHT,
    key.UP: key.UP,
    key.LEFT: key.LEFT,
    key.DOWN: key.DOWN,
    key.RIGHT: key.RIGHT,
    key.ESCAPE: key.ESCAPE,
    key.ENTER: key.ENTER,
    key.B: key.B,
    }
interesting_key = remapped_keys.get

_key_repr = {
    key.UP: "Up",
    key.LEFT: "Left",
    key.DOWN: "Down",
    key.RIGHT: "Right",
    key.ESCAPE: "Escape",
    key.ENTER: "Enter",

    key.B: "B",
    }
key_repr = _key_repr.get

map_legend = {}

def legend(c):
    assert len(c) == 1
    assert c not in map_legend
    def decorator(klass):
        map_legend[c] = klass
        klass.legend = c
        return klass
    return decorator

class MapTile:
    water = False

@legend(".")
class MapWater(MapTile):
    current = (0, 0)
    water = True

@legend("^")
class MapWaterCurrentUp(MapWater):
    current = (0, -1)

@legend("<")
class MapWaterCurrentLeft(MapWater):
    current = (-1, 0)

@legend(">")
class MapWaterCurrentRight(MapWater):
    current = (1, 0)

@legend("v")
class MapWaterCurrentDown(MapWater):
    current = (0, 1)

@legend("X")
class MapBlockage(MapTile):
    current = (0, 0)
    water = True

@legend("#")
class MapLand(MapTile):
    pass

@legend("S")
class MapSpawnPoint(MapTile):
    pass

map_text = """
...v<<<.......................
..#v##^.......................
.##v##^.......................
.#.>>>^.......................
.##.##X.......................
.##.##^.......................
.S#.##^##.....................
.##.####......................
..............................
"""
# .S#.##^.......................
# .S###########################.

map = []

for line in map_text.strip().split("\n"):
    a = []
    map.append(a)
    for c in line:
        a.append(map_legend[c]())

for line in map:
    assert len(line) == len(map[0])

# the map is currently map[y][x].
# now rotate map so x is first instead of y.
# and index by tuple rather than nested list.
# so that we get map[x, y]
# (which is what tmx gives us)
map_width = len(map[0])
map_height = len(map)

new_map = {}
for y, line in enumerate(map):
    for x, tile in enumerate(line):
        new_map[x, y] = tile

map = new_map

class GameState(Enum):
    INVALID = 0
    MAIN_MENU = 1
    LOADING = 2
    PRESHOW = 3
    PLAYING = 4
    PAUSED = 5
    LEVEL_COMPLETE = 6
    GAME_OVER = 7
    GAME_WON = 8
    CONFIRM_EXIT = 9

class Ticker:
    def __init__(self, name, interval, callback=None, *, delay=0):
        """
        interval is how often to tick expressed in seconds.
        fractional seconds are allowed (as floats).

        delay is how long to wait before the first tick, if not the
        same as interval.

        examples:
        Ticker(interval=0.25)
          Ticks four times a second.

        Ticker(interval=0.5, delay=0.8)
          Ticks twice a second.  The first tick is at 0.8 seconds,
          the second at 1.3 seconds, the third at 1.8 seconds, etc.

        Tickers are not automatic.  You must explicitly call advance()
        to tell them that time has elapsed.

        Note that Ticker doesn't actually care what units the times
        are expressed in.  I called 'em seconds but they could just as
        easily be anything else (milliseconds, years, frames).
        """
        assert isinstance(interval, (int, float)) and interval, "must supply a valid (nonzero) interval!  got " + repr(interval)
        self.name = name
        self.interval = interval
        self.callback = callback
        # initial delay
        self.delay = delay
        self.reset()

    # dt is fractional seconds e.g. 0.001357
    def advance(self, dt):
        self.accumulator += dt
        self.elapsed += dt
        callbacks = 0
        while self.accumulator >= self.next:
            self.counter += 1
            callbacks += 1
            self.accumulator -= self.next
            self.next = self.interval
            if self.callback:
                self.callback()
            for t in self.timers:
                t.advance(1)
        return callbacks

    def reset(self):
        self.counter = 0
        self.elapsed = self.accumulator = 0.0
        self.next = self.delay or self.interval
        self.timers = []


class Timer:
    def __init__(self, name, clock, interval, callback=None):
        self.name = name
        self.clock = clock
        self.interval = interval
        self.callback = callback
        self.reset()

    def reset(self):
        self.elapsed = 0
        assert self not in self.clock.timers
        self.clock.timers.append(self)

    def advance(self, dt):
        if self.elapsed >= self.interval:
            return False
        self.elapsed += dt
        if self.elapsed < self.interval:
            return False
        self.elapsed = self.interval
        if self.callback():
            self.callback()
        assert self in self.clock.timers
        self.clock.timers.remove(self)
        return True

    @property
    def ratio(self):
        return self.elapsed / self.interval





_log = []
log_start = time.time()
def log(*a):
    t = time.time()
    s = " ".join(str(x) for x in a)
    _log.append((t, s))

def dump_log():
    print()
    for t, s in _log:
        t -= log_start
        print(f"[{t:8.4f}] {s}")

class Game:
    def __init__(self):
        self.repeater = None

        self.start = time.time()

        self.old_state = self.state = GameState.INVALID
        self.transition_to(GameState.PLAYING)

        # self.renders = Ticker("render", 1/4, self.render)
        self.last_render = -1000
        self.renders = 0

        self.logics = Ticker("logic", logic_interval, self.logic)

        self.key_handler = self

        def make_repeater(key):
            def callback():
                self.on_key(key)
            return callback

        self.repeaters = {}
        for k in (
            key.UP,
            key.DOWN,
            key.LEFT,
            key.RIGHT,
            ):
            rk = make_repeater(k)
            repeater = Ticker(key_repr(k) + " repeater", typematic_interval, rk, delay=typematic_delay)
            repeater.key = k
            self.repeaters[k] = repeater

    def timer(self, dt):
        if self.repeater:
            self.repeater.advance(dt)

        if self.state == GameState.PLAYING:
            self.logics.advance(dt)


    def on_state_PLAYING(self):
        pass

    def transition_to(self, new_state):
        self.state = new_state
        _, _, name = str(new_state).rpartition(".")
        handler = getattr(self, "on_state_" + name, None)
        if handler:
            handler()

    def render(self):
        self.renders += 1
        level.render()

    def logic(self):
        pass

    def on_key_press(self, k, modifier):
        k = interesting_key(k)
        if k:
            # simulate typematic ourselves
            # (we can't use pyglet's on_text_motion because we want this for WASD too)
            repeater = game.repeaters.get(k)
            if repeater:
                repeater.reset()
                self.repeater = repeater
            return self.key_handler.on_key(k)

    def on_key_release(self, k, modifier):
        k = interesting_key(k)
        if k:
            if self.repeater and self.repeater.key == k:
                self.repeater = None

    def on_key(self, k):
        k = interesting_key(k)
        assert k
        if k:
            return self.key_handler.on_key(k)


class Level:
    tiles = pyglet.image.ImageGrid(
        pyglet.resource.image('tilemap.png'),
        rows=8,
        columns=5,
    ).get_texture_sequence()
    tilemap = {
        0b0000: (0, 3),
        0b0001: (2, 2),
        0b0010: (2, 0),
        0b0011: (2, 1),
        0b0100: (0, 0),
        0b0110: (1, 0),
        0b0111: (3, 1),
        0b1000: (0, 2),
        0b1001: (1, 2),
        0b1011: (3, 0),
        0b1100: (0, 1),
        0b1101: (4, 0),
        0b1110: (4, 1),
        0b1111: (1, 1),
    }

    def __init__(self, width, height):
        self.start = time.time()
        self.map = {}
        self.width = width
        self.height = height
        player_position = None
        for coord in self.coords():
            tile = map[coord]
            if isinstance(tile, MapSpawnPoint):
                player_position = coord
                tile = MapLand()
            self.map[coord] = tile

        if not player_position:
            raise Exception("No player position set!")
        self.player = Player(player_position)

        self.build_batch()

    def coords(self):
        """Iterate over coordinates in the level."""
        for y in range(self.height):
            for x in range(self.width):
                yield x, y

    def build_batch(self):
        batch = pyglet.graphics.Batch()
        sprites = []
        def q(x, y):
            t = self.map.get((x, y))
            return bool(t and not t.water)
        for x, y in self.coords():
            bitv = (
                q(x, y) |
                q(x, y - 1) << 1 |
                q(x + 1, y - 1) << 2 |
                q(x + 1, y) << 3
            )
            screenx, screeny = map_to_screen((x, y))
            tx, ty = self.tilemap[bitv]
            sprites.append(
                pyglet.sprite.Sprite(
                    self.tiles[ty, tx],
                    x=screenx,
                    y=screeny,
                    batch=batch,
                )
            )
        self.batch = batch
        self.sprites = sprites





class Animator:
    def __init__(self, clock):
        """
        clock should be a Ticker.
        """
        self.clock = clock

    def animate(self, start, end, interval, callback=None):
        self.start = start
        self.end = end
        self.interval = interval
        self.callback = callback

        self.timer = Timer("animator", self.clock, interval, self._complete)
        self.finished = False

        self.delta_x = end[0] - start[0]
        self.delta_y = end[1] - start[1]

    @property
    def ratio(self):
        return self.timer.ratio

    def _complete(self):
        self.finished = True
        if self.callback:
            self.callback()

    @property
    def position(self):
        ratio = self.timer.ratio
        x, y = self.start
        x += self.delta_x * ratio
        y += self.delta_y * ratio
        return (x, y)


class PlayerOrientation(Enum):
    INVALID = 0
    RIGHT = 1
    UP = 2
    LEFT = 3
    DOWN = 4


key_to_movement_delta = {
    key.UP:    ( 0, -1),
    key.DOWN:  ( 0, +1),
    key.LEFT:  (-1,  0),
    key.RIGHT: (+1,  0),
    }

orientation_to_position_delta = {
    PlayerOrientation.RIGHT: (+1,  0),
    PlayerOrientation.UP:    ( 0, -1),
    PlayerOrientation.LEFT:  (-1,  0),
    PlayerOrientation.DOWN:  ( 0, +1),
    }

key_to_orientation = {
    key.RIGHT: PlayerOrientation.RIGHT,
    key.UP:    PlayerOrientation.UP,
    key.LEFT:  PlayerOrientation.LEFT,
    key.DOWN:  PlayerOrientation.DOWN,
    }


pc_down = load_pc('pc-down.png')
pc_up = load_pc('pc-up.png')
pc_left = load_pc('pc-left.png')
pc_right = load_pc('pc-right.png')

pc_sprite = {
    PlayerOrientation.LEFT:  pc_left,
    PlayerOrientation.RIGHT: pc_right,
    PlayerOrientation.UP:    pc_up,
    PlayerOrientation.DOWN:  pc_down,
    }



class Player:
    def __init__(self, position):
        game.key_handler = self
        self.position = position
        self.screen_position = map_to_screen(position)

        # what should be the player's initial orientation?
        # it doesn't really matter.  let's pick something cromulent.
        #
        # divide up the screen into three sections as such,
        # and have the player face Down, Right, or Left as follows.
        #
        # +-----------+
        # |     D     |
        # |-----------|
        # |  R  |  L  |
        # +-----------+
        x, y = position
        if y <= coords.TILES_H // 2:
            self.orientation = PlayerOrientation.DOWN
        elif x <= coords.TILES_W // 2:
            self.orientation = PlayerOrientation.RIGHT
        else:
            self.orientation = PlayerOrientation.LEFT

        self.animator = Animator(game.logics)
        self.halfway_timer = None
        self.moving = False

    def _finished_animation(self):
        self.moving = False
        self.position = self.new_position
        self.screen_position = self.animator.position

    def on_key(self, k):
        if k == key.B:
            # drop bomb
            delta_x, delta_y = orientation_to_position_delta[level.player.orientation]
            x, y = level.player.position
            bomb_position = x + delta_x, y + delta_y
            if bombs.get(bomb_position):
                return
            TimedBomb(bomb_position)
            return

        delta = key_to_movement_delta.get(k)
        if not delta:
            return

        # for now: once they're moving, they
        # have to finish moving.
        # don't let them change direction
        # or abort the movement, for now.
        # they have to finish it.
        if self.moving:
            return

        desired_orientation = key_to_orientation[k]
        if self.orientation != desired_orientation:
            self.orientation = desired_orientation
            return

        x, y = self.position
        delta_x, delta_y = delta
        new_position = x + delta_x, y + delta_y
        leap_position = x + (delta_x * 2), y + (delta_y * 2)
        tile = map.get(new_position)
        if (not tile) or isinstance(tile, MapWater):
            new_position = leap_position
            tile = map.get(new_position)
            if (not tile) or isinstance(tile, MapWater):
                return

        self.moving = True
        self.new_position = new_position
        self.animator.animate(
            map_to_screen(self.position),
            map_to_screen(new_position),
            player_movement_logics,
            self._finished_animation)

    def render(self):
        spr = pc_sprite[level.player.orientation]
        if self.moving:
            position = self.animator.position
        else:
            position = self.screen_position
        # print("drawing player at", position)
        spr.position = position
        spr.draw()


bombs = {}

timed_bomb = load_sprite('timed-bomb.png')
freeze_bomb = load_sprite('freeze-bomb.png')

exploding_bomb_image = 'freeze-bomb.png'

class Bomb:
    def __init__(self, position):
        self.position = position

    def detonate(self, dt):
        old_sprite_position = self.sprite.position
        self.sprite.delete()
        self.sprite = load_sprite(exploding_bomb_image)
        self.sprite.position = old_sprite_position
        pyglet.clock.schedule_once(self.remove, exploding_bomb_interval)

    def remove(self, dt):
        del bombs[self.position]
        self.sprite.delete()

class TimedBomb(Bomb):
    def __init__(self, position):
        super().__init__(position)
        pyglet.clock.schedule_once(self.detonate, timed_bomb_interval)
        bombs[self.position] = self
        self.sprite = load_sprite('timed-bomb.png')
        self.sprite.position = map_to_screen(position)


window = pyglet.window.Window(coords.WIDTH, coords.HEIGHT)

game = Game()
level = Level(map_width, map_height)


def screenshot_path():
    root = Path.cwd()
    grabs = root / 'grabs'
    grabs.mkdir(exist_ok=True)
    day = (datetime.date.today() - datetime.date(2018, 10, 20)).days
    for n in itertools.count(1):
        path = grabs / f'day{day}-{n}.png'
        if not path.exists():
            return str(path)


@window.event
def on_key_press(k, modifiers):
    if k == key.F12:
        gl.glPixelTransferf(gl.GL_ALPHA_BIAS, 1.0)  # don't transfer alpha channel
        image = pyglet.image.ColorBufferImage(0, 0, window.width, window.height)
        image.save(screenshot_path())
        gl.glPixelTransferf(gl.GL_ALPHA_BIAS, 0.0)  # restore alpha channel transfer
    return game.on_key_press(k, modifiers)

@window.event
def on_key_release(k, modifiers):
    return game.on_key_release(k, modifiers)


grass = load_tile('grass.png')

flow = FlowParticles(level)


@window.event
def on_draw():
    gl.glClearColor(0.5, 0.55, 0.8, 0)
    window.clear()

    flow.batch.draw()
    level.batch.draw()

    if not (level and level.player):
        return

    level.player.render()

    for bomb in bombs.values():
        bomb.sprite.draw()


def timer_callback(dt):
    game.timer(dt)
    flow.update(dt)


pyglet.clock.schedule_interval(timer_callback, callback_interval)
pyglet.app.run()

# dump_log()
