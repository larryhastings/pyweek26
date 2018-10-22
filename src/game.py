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


tiles_x = 64
tiles_y = 40

timed_bomb_interval = 3
exploding_bomb_interval = 1/10

logic_interval = 1/10

typematic_interval = 1/4
typematic_delay = 1

# please ensure all the other intervals
# are evenly divisible into this interval
callback_interval = 1/20


srcdir = Path(__file__).parent
pyglet.resource.path = [
    'images',
]
pyglet.resource.reindex()


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
    pass

@legend(".")
class MapWater(MapTile):
    current = (0, 0)

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
    pass

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
    def __init__(self, name, frequency, callback, *, delay=0):
        assert isinstance(frequency, (int, float)) and frequency, "must supply a valid (nonzero) frequency!  got " + repr(frequency)
        self.name = name
        self.frequency = frequency
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
            self.callback()
            self.counter += 1
            callbacks += 1
            self.accumulator -= self.next
            self.next = self.frequency
        return callbacks

    def reset(self):
        self.counter = 0
        self.elapsed = self.accumulator = 0.0
        self.next = self.delay or self.frequency


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
            return isinstance(t, MapLand)
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


class FlowParticles:
    ripple = pyglet.resource.image('ripple.png')
    RATE = 10

    def __init__(self, level):
        self.level = level
        self.batch = pyglet.graphics.Batch()
        self.particles = []

    def update(self, dt):
        water_tiles = {}
        for pos in self.level.coords():
            t = self.level.map.get(pos)
            if t is None:
                water_tiles[pos] = (0, 0)
            elif isinstance(t, MapWater):
                water_tiles[pos] = t.current

        new_particles = []
        for p in self.particles:
            p.age += dt
            if p.age > 4:
                continue

            if p.age < 1:
                p.opacity = p.age * p.bright
            elif p.age > 3:
                p.opacity = (4 - p.age) * p.bright

            x, y = p.map_pos
            current = water_tiles.get((round(x), round(y)))
            if not current:
                continue
            curx, cury = current

            vx, vy = p.v

            frac = 0.5 ** dt
            invfrac = 1.0 - frac
            vx = frac * vx + invfrac * curx
            vy = frac * vy + invfrac * cury

            p.v = vx, vy
            x += vx * dt * 0.3
            y += vy * dt * 0.3
            p.map_pos = x, y
            p.position = map_to_screen(p.map_pos)
            new_particles.append(p)

        for (tx, ty), current in water_tiles.items():
            if random.uniform(0, 3) > dt:
                continue
            x = random.uniform(tx - 0.5, tx + 0.5)
            y = random.uniform(ty - 0.5, ty + 0.5)

            map_pos = x, y
            sx, sy = map_to_screen(map_pos)
            p = pyglet.sprite.Sprite(
                self.ripple,
                sx,
                sy,
                batch=self.batch
            )
            p.age = 0
            p.bright = random.uniform(128, 255)
            cx, cy = current
            p.v = (
                cx + random.uniform(-0.5, 0.5),
                cy + random.uniform(-0.5, 0.5)
            )
            p.opacity = 0
            p.scale = random.uniform(0.2, 0.3)
            p.map_pos = map_pos
            new_particles.append(p)
        self.particles = new_particles


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


class Player:
    def __init__(self, position):
        game.key_handler = self
        self.position = position

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
        if y <= (tiles_y // 2):
            self.orientation = PlayerOrientation.DOWN
        elif x <= (tiles_x // 2):
            self.orientation = PlayerOrientation.RIGHT
        else:
            self.orientation = PlayerOrientation.LEFT

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
        self.position = new_position


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


window = pyglet.window.Window()

def map_to_screen(pos):
    x, y = pos
    return x * tiles_x + 100, window.height - 100 - y * tiles_y

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

    spr = pc_sprite[level.player.orientation]
    spr.position = map_to_screen(level.player.position)
    spr.draw()

    for bomb in bombs.values():
        bomb.sprite.draw()


def timer_callback(dt):
    game.timer(dt)
    flow.update(dt)


pyglet.clock.schedule_interval(timer_callback, callback_interval)
pyglet.app.run()

# dump_log()
