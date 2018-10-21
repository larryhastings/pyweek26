#!/usr/bin/env python3
from enum import Enum
from pathlib import Path
from pyglet import gl
import pyglet.window.key as key
import pyglet.window.key
import pyglet.resource
import sys
import time


srcdir = Path(__file__).parent
pyglet.resource.path = [
    'images',
]
pyglet.resource.reindex()

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
    }

interesting_key = remapped_keys.get

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
    pass

@legend("^")
class MapWaterCurrentUp(MapWater):
    pass

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
......X.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.S#.##^.......................
.##.##........................
..............................
"""

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
    def __init__(self, name, hz, callback, *, delay=0):
        self.name = name
        self.callback = callback
        # initial delay
        self.delay = delay
        self.hz = hz
        self.reset()

    # dt is fractional seconds e.g. 0.001357
    def advance(self, dt):
        old_elapsed = self.elapsed
        self.elapsed += dt * self.hz
        # print("ADVANCING", self.name, old_elapsed, "=>", self.elapsed, self.delaying, self.delay)
        callbacks = 0
        if self.delaying:
            if self.elapsed < self.delay:
                # print("TOO SOON", self.elapsed, "<", self.delay)
                return
            self.delaying = False
            self.elapsed -= self.delay
            # print("FINISHED DELAY, CALLING CALLBACK", self.name, self.callback)
            self.callback()
            callbacks += 1
        floored_elapsed = int(self.elapsed)
        while self.counter < floored_elapsed:
            # print("CALLING CALLBACK", self.name, self.callback)
            self.callback()
            self.counter += 1
            callbacks += 1
        return callbacks

    def reset(self):
        self.counter = self.elapsed = 0
        self.delaying = bool(self.delay)


class Game:
    def __init__(self):
        self.repeater = None

        self.start = time.time()

        self.old_state = self.state = GameState.INVALID
        self.transition_to(GameState.PLAYING)

        self.renders = Ticker("render", 4, self.render)
        self.logics = Ticker("logic", 120, self.logic)

        self.key_handler = self

        def make_repeater(name, key):
            def callback():
                self.on_key(key)
            return callback

        self.repeaters = {}
        for name, k in (
            ("up", key.UP),
            ("down", key.DOWN),
            ("left", key.LEFT),
            ("right", key.RIGHT),
            ):
            rk = make_repeater(name, k)
            repeater = Ticker(name + " repeater", 4, rk, delay=1)
            repeater.key = k
            self.repeaters[k] = repeater


    def timer(self, dt):
        # print("TIMER", dt)
        if self.repeater:
            self.repeater.advance(dt)

        if self.state == GameState.PLAYING:
            self.logics.advance(dt)

        self.renders.advance(dt)

    def on_state_PLAYING(self):
        print("playing! ")
        pass

    def transition_to(self, new_state):
        _, _, name = str(new_state).rpartition(".")
        handler = getattr(self, "on_state_" + name, None)
        if handler:
            handler()

    def render(self):
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


def clear_screen():
    print("\033[2J\033[H", end="")
    # pass

class Level:
    def __init__(self):
        self.start = time.time()
        self.player = Player()
        self.map = {}
        for y in range(map_height):
            for x in range(map_width):
                coord = x, y
                tile = map[coord]
                if isinstance(tile, MapSpawnPoint):
                    self.player.position = coord
                    tile = MapLand()
                self.map[coord] = tile

    def render(self):
        clear_screen()
        elapsed = time.time() - self.start
        print(f"{elapsed:05.1f}")
        text = []
        for y in range(map_height):
            for x in range(map_width):
                coord = x, y
                if self.player.position == coord:
                    text.append("O")
                    continue
                tile = self.map[coord]
                text.append(tile.legend)
            text.append("\n")
        print("".join(text))
        print("player", self.player.position)
        # if game.repeater:
            # print("repeater now set for key", game.repeater.key)


class Player:
    def __init__(self):
        game.key_handler = self

    def on_key(self, k):
        x, y = self.position
        leap_x, leap_y = x, y
        if k == key.UP:
            y = y - 1
            leap_y = y - 2
        if k == key.DOWN:
            y = y + 1
            leap_y = y + 2
        if k == key.LEFT:
            x = x - 1
            leap_x = x - 2
        if k == key.RIGHT:
            x = x + 1
            leap_x = x + 2
        new_coord = x, y
        tile = map.get(new_coord)
        if (not tile) or isinstance(tile, MapWater):
            new_coord = leap_x, leap_y
            tile = map.get(new_coord)
            if (not tile) or isinstance(tile, MapWater):
                return
        self.position = new_coord



window = pyglet.window.Window()
game = Game()
level = Level()


@window.event
def on_key_press(key, modifiers):
    return game.on_key_press(key, modifiers)

@window.event
def on_key_release(key, modifiers):
    return game.on_key_release(key, modifiers)


def load_pc(name):
    """Load a PC sprite and set the anchor position."""
    pc = pyglet.resource.image(name)
    pc.anchor_x = pc.width // 2
    pc.anchor_y = 10
    return pc


def load_tile(name):
    """Load a ground tile and set the anchor position."""
    img = pyglet.resource.image(name)
    img.anchor_x = img.width // 2
    img.anchor_y = img.height // 2
    return img


pc = load_pc('pc-s.png')
grass = load_tile('grass.png')
spr = pyglet.sprite.Sprite(pc)


def map_to_screen(pos):
    x, y = pos
    return x * 64 + 100, window.height - 100 - y * 40


@window.event
def on_draw():
    gl.glClearColor(0.5, 0.55, 0.8, 0)
    window.clear()
    for y in range(map_height):
        for x in range(map_width):
            coord = x, y
            t = level.map.get(coord)
            if isinstance(t, MapLand):
                grass.blit(*map_to_screen(coord))

    spr.position = map_to_screen(level.player.position)
    spr.draw()


def timer_callback(dt):
    game.timer(dt)

pyglet.clock.schedule_interval(timer_callback, 1/240)
pyglet.app.run()
