#!/usr/bin/env python3
from enum import Enum
import pyglet.window
from pyglet.window import key
import sys
import time


map = """
......X.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.##.##^.......................
.S#.##^.......................
.##.##........................
..............................
""".strip()


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


class Game:
    def __init__(self):
        self.start = time.time()

        self.old_state = self.state = GameState.INVALID
        self.transition_to(GameState.PLAYING)

        self.logics = 0
        self.logics_clock = 0

        self.renders = 0
        self.render_clock = 0

    def timer(self, dt):
        render_delta = dt * 24
        self.render_clock += render_delta
        floored = int(self.render_clock)
        while self.renders < floored:
            self.renders += 1
            self.render()

        if self.state == GameState.PLAYING:
            logics_delta = dt * 120
            self.logics_clock += logics_delta
            floored = int(self.logics_clock)
            while self.logics < floored:
                self.logics += 1
                self.logic()

    def on_state_PLAYING(self):
        print("playing!")

    def transition_to(self, new_state):
        _, _, name = str(new_state).rpartition(".")
        handler = getattr(self, "on_state_" + name, None)
        if handler:
            handler()
        sys.exit(0)

    def render(self):
        level.render()

    def logic(self):
        pass


def clear_screen():
    print("\033[2J\033[H", end="")

class Level:
    def __init__(self):
        self.start = time.time()

    def render(self):
        clear_screen()
        elapsed = time.time() - self.start
        print(f"{elapsed:05.1f}")
        print(map)


class Player:
    def __init__(self):
        pass



window = pyglet.window.Window()
game = Game()
level = Level()
player = Player()

up_keys =     frozenset((key.UP,    key.W,))
left_keys =   frozenset((key.LEFT,  key.A,))
down_keys =   frozenset((key.DOWN,  key.S,))
right_keys =  frozenset((key.RIGHT, key.D,))
escape_keys = frozenset((key.ESCAPE,))

@window.event
def on_key_press(symbol, modifiers):
    if symbol in up_keys:
        print("UP")


def timer_callback(dt):
    game.timer(dt)

pyglet.clock.schedule_interval(timer_callback, 1/240)
pyglet.app.run()
