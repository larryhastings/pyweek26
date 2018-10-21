#!/usr/bin/env python3
from enum import Enum
import pyglet.window.key as key
import pyglet.window.key
import sys
import time

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
    }
interesting_key = remapped_keys.get

_key_repr = {
    key.UP: "Up",
    key.LEFT: "Left",
    key.DOWN: "Down",
    key.RIGHT: "Right",
    key.ESCAPE: "Escape",
    key.ENTER: "Enter",
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
            # log(f"{self.name} {self.counter} {self.elapsed}")
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
        self.logics = Ticker("logic", 1/120, self.logic)

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
            repeater = Ticker(key_repr(k) + " repeater", 1/4, rk, delay=1.0)
            repeater.key = k
            self.repeaters[k] = repeater

    def invalidate_screen(self):
        log("invalidate screen")
        t = time.time()
        delta = t - self.last_render
        if delta >= 1/8:
            self.last_render = t
            self.render()


    def timer(self, dt):
        # print("TIMER", dt)
        if self.repeater:
            self.repeater.advance(dt)

        if self.state == GameState.PLAYING:
            self.logics.advance(dt)

        # self.renders.advance(dt)

    def on_state_PLAYING(self):
        print("playing! ")
        pass

    def transition_to(self, new_state):
        _, _, name = str(new_state).rpartition(".")
        handler = getattr(self, "on_state_" + name, None)
        if handler:
            handler()

    def render(self):
        # log("render", self.renders.counter)
        log("render", self.renders)
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
                log(f"starting repeater {key_repr(repeater.key)}")
                repeater.reset()
                self.repeater = repeater
            return self.key_handler.on_key(k)

    def on_key_release(self, k, modifier):
        k = interesting_key(k)
        if k:
            if self.repeater and self.repeater.key == k:
                log(f"removing repeater {key_repr(self.repeater.key)}")
                self.repeater = None

    def on_key(self, k):
        k = interesting_key(k)
        assert k
        if k:
            return self.key_handler.on_key(k)


clear_screen_s = "\033[2J\033[H"
#clear_screen_s = ""
def clear_screen():
    print(clear_screen_s, end="")

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
        # clear_screen()
        elapsed = time.time() - self.start
        text = [clear_screen_s, f"{elapsed:05.1f}\n"]
        for y in range(map_height):
            for x in range(map_width):
                coord = x, y
                if self.player.position == coord:
                    text.append("O")
                    continue
                tile = self.map[coord]
                text.append(tile.legend)
            text.append("\n")
        text.append(f"player {self.player.position}")
        sys.stdout.write("".join(text))
        sys.stdout.flush()
        # if game.repeater:
            # print("repeater now set for key", game.repeater.key)


class Player:
    def __init__(self):
        game.key_handler = self

    def on_key(self, k):
        r = key_repr(k)
        t = time.time()
        log(f"{r}")
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
        game.invalidate_screen()



window = pyglet.window.Window()
game = Game()
level = Level()


@window.event
def on_key_press(key, modifiers):
    return game.on_key_press(key, modifiers)

@window.event
def on_key_release(key, modifiers):
    return game.on_key_release(key, modifiers)


def timer_callback(dt):
    game.timer(dt)


game.invalidate_screen()
pyglet.clock.schedule_interval(timer_callback, 1/250)
pyglet.app.run()

dump_log()