#!/usr/bin/env python3
import collections
import datetime
from enum import Enum, IntEnum
import itertools
from pathlib import Path
import random
import sys
import time
import math
import copy

from pyglet import clock, gl
from pyglet.text import Label
import pyglet.image
import pyglet.resource
import pyglet.window.key
import pyglet.window.key as key

from dynamite import coords
from dynamite.particles import FlowParticles
from dynamite.level_renderer import LevelRenderer
import dynamite.scene
from dynamite.maploader import load_map
from dynamite.vec2d import Vec2D
from dynamite.animation import animate as tween
from dynamite.titles import TitleScreen, Screen, IntroScreen, BackStoryScreen, GameWonScreen
from dynamite.titles import BODY_FONT

TITLE = "Dynamite Valley"


if '--no-tween' in sys.argv:
    def tween(obj, tween=None, duration=None, on_finished=None, **targets):
        for k, v in targets.items():
            setattr(obj, k, v)
        if on_finished:
            on_finished()


# please ensure all the other intervals
# are evenly divisible into this interval
logics_per_second = 120
logic_interval = 1 / logics_per_second

typematic_start = 0.15
typematic_interval = 1/4
typematic_delay = 1

timed_bomb_interval = 5 * logics_per_second
exploding_bomb_interval = (1/10) * logics_per_second
contact_bomb_detonation_interval = (2/10) * logics_per_second

callback_interval = logic_interval


player_movement_logics = typematic_interval * logics_per_second
player_movement_delay_logics = typematic_start * logics_per_second

water_speed_logics = 1 * logics_per_second
explosion_push_logics = logics_per_second / 10
fling_movement_logics = logics_per_second / 10
freeze_detonation_interval = 2 * logics_per_second
freeze_timer_logics = 5 * logics_per_second

srcdir = Path(__file__).parent
pyglet.resource.path = [
    'images',
    'levels',
    'sounds',
]
pyglet.resource.reindex()
pyglet.resource.add_font('edo.ttf')

LevelRenderer.load()
FlowParticles.load()

cant_play_audio = False

class SafePlayer:
    def __init__(self, *a, **k):
        self.player = None
        try:
            self.media = pyglet.resource.media(*a, **k)
        except pyglet.media.sources.riff.WAVEFormatException:
            global cant_play_audio
            cant_play_audio = True
            self.media = None

    def play(self):
        if self.media:
            self.player = self.media.play()

    def pause(self):
        if self.player:
            self.player.pause()


remapped_keys = {
    key.ESCAPE: key.ESCAPE,
    key.ENTER: key.ENTER,
    key.SPACE: key.SPACE,

    key.W: key.UP,
    key.A: key.LEFT,
    key.S: key.DOWN,
    key.D: key.RIGHT,

    key.UP: key.UP,
    key.LEFT: key.LEFT,
    key.DOWN: key.DOWN,
    key.RIGHT: key.RIGHT,

    key.B: key.B,
    key.E: key.E,
    key.L: key.L,
    key.T: key.T,
}

interesting_key = remapped_keys.get

_key_repr = {
    key.ESCAPE: "Escape",
    key.ENTER: "Enter",
    key.SPACE: "Space",

    key.UP: "Up",
    key.LEFT: "Left",
    key.DOWN: "Down",
    key.RIGHT: "Right",

    key.B: "B",
    key.E: "E",
    key.L: "L",
    key.T: "T",
    }
key_repr = _key_repr.get

OCCUPIABLE_BY_PLAYER = 1
OCCUPIABLE_BY_BOMB   = 2


class TileMeta(type):
    def __add__(self, ano):
        return self() + ano


class MapTile(metaclass=TileMeta):
    water = False
    moving_water = False
    spawn_item = None
    navigability = OCCUPIABLE_BY_PLAYER | OCCUPIABLE_BY_BOMB
    obj_factory = None

    def spawn_item(self, pos=None):
        if pos is None:
            return None
        if self.obj_factory:
            return self.obj_factory(pos)

    def __add__(self, ano):
        if self.obj_factory:
            raise TypeError(f"{self} already has an obj_factory")
        o = copy.copy(self)
        o.obj_factory = ano
        return o

class MapOOB(MapTile):
    water = False
    moving_water = False
    spawn_item = None
    obj_factory = None
    navigability = 0


class MapWater(MapTile):
    current = Vec2D(0, 0)
    water = True
    navigability = OCCUPIABLE_BY_BOMB


class MapMovingWater(MapWater):
    moving_water = True

class MapWaterCurrentUp(MapMovingWater):
    current = Vec2D(0, -1)

class MapWaterCurrentLeft(MapMovingWater):
    current = Vec2D(-1, 0)

class MapWaterCurrentRight(MapMovingWater):
    current = Vec2D(1, 0)

class MapWaterCurrentDown(MapMovingWater):
    current = Vec2D(0, 1)



class MapGrass(MapTile):
    navigability = OCCUPIABLE_BY_PLAYER | OCCUPIABLE_BY_BOMB


class LandSpawn(MapGrass):
    def __init__(self, entity_type, *args, **kwargs):
        self.type = entity_type
        self.args = args
        self.kwargs = kwargs

    def spawn_item(self, pos):
        return self.type(pos, *self.args, **self.kwargs)


class MapScenery(MapGrass):
    def __init__(self, sprite):
        self.sprite = sprite

    def spawn_item(self, pos):
        return Scenery(pos, self.sprite)



class Clock:
    """
    A discrete clock based on an external time source.
    Used, for example, as the "game logic" clock--you feed
    in time, and it tells you when it's time to calculate
    the next logical positions.

    (Want to pause?  Just temporarily stop feeding in time.)
    """
    def __init__(self, name, interval, callback=None, *, delay=0):
        """
        interval is how often to tick expressed in seconds.
        fractional seconds are allowed (as floats).

        delay is how long to wait before the first tick, if not the
        same as interval.

        examples:
        Clock(interval=0.25)
          Ticks four times a second.

        Clock(interval=0.5, delay=0.8)
          Ticks twice a second.  The first tick is at 0.8 seconds,
          the second at 1.3 seconds, the third at 1.8 seconds, etc.

        Clocks are not automatic.  You must explicitly call advance()
        to tell them that time has elapsed.

        Note that Clock doesn't actually care what units the times
        are expressed in.  I called 'em seconds but they could just as
        easily be anything else (milliseconds, years, frames).
        """
        assert isinstance(interval, (int, float)) and interval, "must supply a valid (nonzero) interval!  got " + repr(interval)
        self.counter = self.elapsed = self.next = 0
        self.name = name
        self.interval = interval
        self.callback = callback
        # initial delay
        self.delay = delay
        self.reset()

    def __repr__(self):
        return f"Clock({self.name}, {self.counter}, {self.elapsed} / {self.next})"

    # dt is fractional seconds e.g. 0.001357
    def advance(self, dt):
        if self.paused:
            log(f"{self} {dt} PAUSED")
            return

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
            # TODO a callback might remove a timer
            # which means we'd be modifying the list
            # while iterating which I think is still bad
            for t in self.timers:
                t.advance(1)
        return callbacks

    def reset(self):
        self.counter = 0
        self.elapsed = self.accumulator = 0.0
        self.next = self.delay or self.interval
        self.paused = False
        self.timers = []


class Timer:
    def __init__(self, name, clock, interval, end_callback=None, on_tick=None):
        self.name = name
        self.clock = clock
        self.interval = interval
        self.callback = end_callback
        self.on_tick = on_tick
        self.reset()

    def __repr__(self):
        return f"Timer({self.name}, {self.clock}, {self.interval}, callback={self.callback}, on_tick={self.on_tick})"

    def reset(self):
        self.elapsed = 0
        self.paused = False
        assert self not in self.clock.timers
        self.clock.timers.append(self)

    def cancel(self):
        if self in self.clock.timers:
            self.clock.timers.remove(self)
        # else:
        #     print(f"[{game.logics.counter:05} warning: couldn't find timer for {self.name}")

    def advance(self, dt):
        if self.paused:
            return False
        if self.elapsed >= self.interval:
            return False
        self.elapsed += dt
        if self.on_tick:
            self.on_tick()
        if self.elapsed < self.interval:
            return False
        self.elapsed = self.interval
        if self.callback():
            self.callback()
        self.cancel()
        return True

    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    @property
    def ratio(self):
        return self.elapsed / self.interval


log_start_time = time.time()

_logfile = open("dv.log.txt", "wt")

def log(*a):
    outer = sys._getframe(1)
    fn = outer.f_code.co_name
    lineno = outer.f_lineno
    elapsed = time.time() - log_start_time
    s = " ".join(str(x) for x in a)
    line = f"[{elapsed:07.3f}:{game.logics.counter:5}] {fn}()@{lineno} {s}"
    print(line)
    print(line, file=_logfile)

if not __debug__:
    def log(*a):
        pass



def send_message(o, message, *a):
    """
    Safely calls a method on an object.
    If the object doesn't have that method, returns None.
    """
    fn = getattr(o, message, None)
    if not fn:
        return None
    return fn(*a)

class Game:
    def __init__(self):
        self.repeater = None

        self.start = time.time()

        self.logics = Clock("logic", logic_interval, self.logic)

        self.key_handler = self

        self.paused = False

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
            repeater = Clock(key_repr(k) + " repeater", typematic_interval, rk, delay=typematic_delay)
            repeater.key = k
            self.repeaters[k] = repeater

    def timer(self, dt):
        if self.repeater:
            self.repeater.advance(dt)

        if not self.paused:
            # log(f"logics {self.logics} advance by dt {dt}")
            self.logics.advance(dt)

    def transition_to(self, new_state):
        self.state = new_state
        _, _, name = str(new_state).rpartition(".")
        send_message(self, "on_state_" + name)

    def logic(self):
        pass

    def pause(self):
        if self.paused:
            return
        self.paused = True

    def unpause(self):
        if not self.paused:
            return
        self.paused = False

    def on_key_press(self, k, modifier):
        k = interesting_key(k)
        if k:
            # simulate typematic ourselves
            # (we can't use pyglet's on_text_motion because we want this for WASD too)
            repeater = game.repeaters.get(k)
            if repeater:
                repeater.reset()
                self.repeater = repeater
            r1 = send_message(self.key_handler, "on_key_press", k)
            r2 = send_message(self.key_handler, "on_key", k)
            return r1 or r2

    def on_key_release(self, k, modifier):
        k = interesting_key(k)
        if k:
            if self.repeater and self.repeater.key == k:
                self.repeater = None
            return send_message(self.key_handler, "on_key_release", k)

    def on_key(self, k):
        k = interesting_key(k)
        assert k
        if k:
            return send_message(self.key_handler, "on_key", k)


class Level:
    DEFAULT = MapOOB

    def set_map(self, map_data):
        self.map = map_data.tiles
        self.width = map_data.width
        self.height = map_data.height
        self.tile_occupant = collections.defaultdict(None.__class__)
        self.tile_queue = collections.defaultdict(list)

        for coord in self.coords():
            tile = self.get(coord)
            if tile.spawn_item:
                occupant = level.tile_occupant[coord]
                if occupant:
                    assert isinstance(occupant, Claim)
                    occupant.superceded()
                o = tile.spawn_item(coord)
                if isinstance(o, Player):
                    if self.player:
                        sys.exit(f"Player set twice!  at {self.player.position} and {o.position}")
                    self.player = o

        if not self.player:
            raise Exception("No player position set!")

    def __init__(self):
        self.serial_number = level_number
        self.start = time.time()
        self.player = None
        self.dams_remaining = 0

    def __repr__(self):
        return f'<Level #{self.serial_number}>'

    def get(self, pos):
        return self.map.get(pos) or self.DEFAULT

    def coords(self):
        """Iterate over coordinates in the level."""
        for y in range(self.height):
            for x in range(self.width):
                yield Vec2D(x, y)

    def top_entity(self, coords):
        """Get the top entity at the given coordinates, or None if empty."""
        return self.tile_occupant[coords]

    def on_dam_spawned(self, dam):
        self.dams_remaining += 1

    def on_dam_destroyed(self, dam):
        self.dams_remaining -= 1
        if not self.dams_remaining:
            self.complete()

    def complete(self):
        log(f"{self} level finished")
        game_screen.hide_hud()

        try:
            with pyglet.resource.file(_next_level_filename(), 'rt') as f:
                pass
        except pyglet.resource.ResourceNotFoundException:
            return self.game_won()

        game_screen.show_level_complete()
        self.on_space_pressed = next_level

    def player_died(self):
        log(f"{self} player was harmed")
        game_screen.show_death_msg()
        self.on_space_pressed = reload_level

    def game_won(self):
        log(f"{self} you win!")
        game_screen.display_big_text_and_wait("YOU WON!")
        self.on_space_pressed = title_screen
        # game.key_handler = self
        # GameWonScreen(window, on_finished=title_screen)

    def pause(self):
        if game.paused:
            return
        log(f"{self} Pausing game.")
        self.on_esc_pressed = self.unpause
        self.on_y_pressed = title_screen
        game.pause()
        game_screen.display_big_text_and_wait("PAUSED", "Abort game? Press Esc to resume game, press Y to abort game.")

    def unpause(self):
        if not game.paused:
            return
        game.unpause()




class Animator:
    def __init__(self, clock):
        """
        clock should be a Clock.
        """
        self.clock = clock
        self.timer = self.halfway_timer = None
        self.obj = self.start = self.end = None

    def __repr__(self):
        return f"Animator({self.obj}, {self.start}, {self.end}, {self.ratio})"

    def animate(self, obj, property, end, interval, callback=None, halfway_callback=None, tick_callback=None):
        self.cancel()

        self.obj = obj
        self.property = property
        start = self.start = getattr(obj, property)
        self.end = end

        self.interval = interval
        self.callback = callback
        self.halfway_callback = halfway_callback
        self.tick_callback = tick_callback
        self.ratio_offset = 0

        self.timer = Timer("animator", self.clock, interval, self._complete, on_tick=self._on_tick)
        if halfway_callback:
            self.halfway_timer = Timer("animator halfway", self.clock, interval / 2, self._halfway)

        self.finished = False

    def cancel(self):
        if self.halfway_timer:
            self.halfway_timer.cancel()
            self.halfway_timer = None
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self.obj = self.property = None
        self.occupant = None

    def reroute(self, destination):
        """
        Change our animation to smoothly animate to a new position.
        Don't start the timer over.  Instead, recalculate so that
        we start at the exact current (animated) spot, end up
        at the new position, and finish at the same time we would
        have if we hadn't been rerouted.
        """
        log(f"{self} rerouting to {destination}")
        current_position = self.position
        ratio_offset = self.ratio

        self.start = current_position
        self.end = destination
        self.ratio_offset = self.ratio

    def pause(self):
        self.timer.pause()
        if self.halfway_timer:
            self.halfway_timer.pause()

    def unpause(self):
        self.timer.unpause()
        if self.halfway_timer:
            self.halfway_timer.unpause()

    @property
    def ratio(self):
        if not self.timer:
            return 0
        return self.timer.ratio

    def _halfway(self):
        self.halfway_timer = None
        self.halfway_callback()

    def _on_tick(self):
        setattr(self.obj, self.property, self.position)
        if self.tick_callback:
            self.tick_callback()

    def _complete(self):
        self.finished = True
        if self.callback:
            self.callback()

    @property
    def position(self):
        if self.end is None:
            return self.start
        if self.start is None:
            return self.end
        ratio = self.ratio
        if self.ratio_offset:
            range = 1 - self.ratio_offset
            ratio = (ratio - self.ratio_offset) / range
        return self.start + ((self.end - self.start) * ratio)

def walk_vec2d_back_to_zero(v):
    yield v
    delta_x = Vec2D(-1 if v.x > 0 else 1, 0)
    delta_y = Vec2D(0, -1 if v.y > 0 else 1)
    while v:
        if abs(v.y) > abs(v.x):
            v += delta_y
        else:
            v += delta_x
        yield v

if 0:
    print(list(walk_vec2d_back_to_zero(Vec2D(-3, 0))))
    print(list(walk_vec2d_back_to_zero(Vec2D(0, 3))))
    print(list(walk_vec2d_back_to_zero(Vec2D(-5, 3))))
    print(list(walk_vec2d_back_to_zero(Vec2D(-1, 1))))
    print(list(walk_vec2d_back_to_zero(Vec2D(3, -5))))
    sys.exit(0)

class Fling:
    def __init__(self, entity, original_delta, delta):
        self.entity = entity
        self.original_delta = original_delta
        self.delta = delta
        self.destination = self.entity.position + delta


entity_serial_numbers = 0
class Entity:
    # are we a platform that other things can go on?
    is_platform = False

    # the entity we're currently standing on (if any).
    # managed automatically for us by the "position" property.
    standing_on = None

    # the entity that's standing on us (if any).
    occupant = None

    # a proxy you use to claim a tile that
    # you're not on right now, but which you
    # want to animate to.
    claim = None

    # a tile we're animating to but is currently occupied.
    queued_tile = None

    # are we moving?
    moving = False

    # if we're moving, where are we moving to?
    moving_to = None

    # we've been flung across the map!
    _fling = None

    # are we a floating object?
    floating = False

    freeze_timer = None

    @classmethod
    def factory(cls, *args, **kwargs):
        """Create a factory for entities of this type."""
        return lambda position: cls(position, *args, **kwargs)

    def __init__(self, position):
        global entity_serial_numbers
        entity_serial_numbers += 1
        self.serial_number = entity_serial_numbers
        log(repr(self))

        self.position = position
        if not isinstance(self, Claim):
            self.claim = Claim(self)

    def on_level_loaded(self):
        pass

    def __repr__(self):
        return f'<{self.__class__.__name__} #{self.serial_number} {self.position}>'

    def queue_for_tile(self, coord):
        assert self.queued_tile == None, f"{self} queued_tile is {self.queued_tile}, should be None"
        log(f"{self} queueing for {coord}")
        self.queued_tile = coord
        level.tile_queue[coord].append(self)
        log(f"level.tile_queue[{coord}] is now {level.tile_queue[coord]}")

    def unqueue_for_tile(self):
        if self.queued_tile:
            log(f"{self} unqueueing for {self.queued_tile}")
            log(f"level.tile_queue[{self.queued_tile}] is currently {level.tile_queue[self.queued_tile]}")
            level.tile_queue[self.queued_tile].remove(self)
            self.queued_tile = None

    def on_tile_available(self, entity, coord):
        """
        entity was on the tile at coord.
        but it has just left.
        """
        pass

    _position = None
    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        if (position is not None) and (not isinstance(position, Vec2D)):
            position = Vec2D(position)

        if self._position == position:
            return

        old_position = self._position
        self._position = position

        departed_tile = None

        if position is not None:
            new_occupant = level.tile_occupant.get(position)
        else:
            new_occupant = None

        if old_position is not None:
            old_occupant = level.tile_occupant[old_position]
            if old_occupant == self:
                log(f"{self} departing {old_position}, clearing level.tile_occupant.")
                level.tile_occupant[old_position] = None
                departed_tile = old_position
            elif self.standing_on == old_occupant:
                log(f"{self} departing {old_position}, stepping off {old_occupant}.")
                old_occupant.on_stepped_on(None)
                self.standing_on = None
            elif self.standing_on and (self.standing_on == new_occupant):
                # if what we're standing on moved to this new position,
                # guess what! the platform moved! we're not stepping off!
                log(f"{self} departing {old_position}, apparently riding on {new_occupant}.")
                pass
            elif self._fling:
                # we're being flung.  our old position was a mystery for the ages.
                # hopefully our final destination will be less so.
                log(f"{self} departing {old_position}, being flung.")
            else:
                log(f"{self} departing {old_position}, but I don't understand how. old_occupant {old_occupant} new_occupant {new_occupant} standing_on {self.standing_on} _fling {self._fling}.")
            #     assert False, f"{self}: I don't understand how we used to be on {old_position}, occupant is {old_occupant} and self.standing_on is {self.standing_on}"

        if position is not None:
            if new_occupant and (new_occupant == self.claim):
                log(f"{self} clearing our claim on this tile.")
                # moving to our claimed tile
                new_occupant = None
                # MILD HACK don't use descriptor to assign here
                # the claim will think it's departing the tile
                # and call on_tile_available() on the next queued guy
                self.claim._position = None
            if new_occupant == None:
                log(f"{self} moving to {position}, tile is not occupied by anyone.")
                level.tile_occupant[position] = self
            elif new_occupant.is_platform:
                assert new_occupant.occupant in (None, self, self.claim), f"we can't step on {new_occupant}, it's occupied by {new_occupant.occupant}"
                log(f"{self} moving to {position}, stepping onto existing tile occupant {new_occupant}")
                self.standing_on = new_occupant
                new_occupant.on_stepped_on(self)
            else:
                log(f"{self} moving to {position}, but I don't understand how, it's occupied by {new_occupant} and we can't step on it.")
                #     assert False, f"{self}: I don't understand how we can move to {position}"

        if departed_tile:
            # tell the next entity in the queue
            # that they can have our old tile
            tq = level.tile_queue[old_position]
            if tq:
                # DON'T remove e from tile_queue here
                # let the entity do that itself!
                e = tq[0]
                assert e.position != old_position
                log(f"{self} departing tile {departed_tile}.  hey, {e}! you can have it!")
                e.on_tile_available(self, old_position)
                new_occupant = level.tile_occupant[old_position]
                assert (new_occupant == e) or (e.claim and new_occupant == e.claim), f"(new_occupant {new_occupant} == e {e}) or (e.claim {e.claim} and new_occupant {new_occupant} == e.claim {e.claim})"

        self.on_position_changed()

    def fling(self, delta):
        """
        This pawn has been flung across the map!
        Move it rapidly (animated) by delta.

        While being flung, we are _not_ occupying the tiles
        we fly over.

        When the fling is over, we occupy the destination tile.
            * This means we "claim" it.
            * If the fling is over more than one space (e.g. delta is (-2, 0)),
              and we can't occupy the destination space, try the closer spaces
              (e.g. try delta (-1, 0)).  if we can claim one of those, fling to that.
            * if we can't claim any of the spaces, the fling fails.
              * Bombs that attempt to be flung and fail explode.

        Note that the rules are a little different for some flung objects.
        If you fling a log, and it wants to land on a space currently occupied
        by a dam, the fling fails.

        **But!**

        If you fling a bomb, and it wants to land on a space currently occupied
        by a dam, and the dam itself is unoccupied, the fling succeeds!  Because
        we want the bomb to skip along platforms like that.  So: we have to ask
        the entity "is it okay for you to be flung onto this entity?".  That's
        what fling_destination_is_okay() is for.  And when the fling is over,
        and the bomb is landing on a platform where we want to re-fling, that's
        what on_fling_completed() is for.
        """
        occupant_is_a_claim = False
        for v in walk_vec2d_back_to_zero(delta):
            log(f"trying delta {v}")
            if not v:
                log(f"fling failed, we walked back to zero without finding any viable spot.")
                return self.on_fling_failed(fling)
            fling = Fling(self, delta, v)
            occupant = level.tile_occupant[fling.destination]
            occupant_is_a_claim = isinstance(occupant, Claim)
            if ((not occupant)
                or occupant_is_a_claim
                or self.fling_destination_is_okay(fling, occupant)):
                break
            log(f"tile wasn't okay, occupant is {occupant}")

        # fling is okay!
        log(f"{self} being flung to {fling.destination}!")
        self._fling = fling
        if self.animator:
            log(f"{self} being animated to new position.")
            if occupant_is_a_claim:
                occupant.superceded()
            self.claim.position = fling.destination
            self.animator.cancel()
            self.animator.animate(
                self.actor, 'position',
                fling.destination,
                fling_movement_logics,
                self.on_fling_completed)
            self.position = None
            self.moving = True
            self.moving_to = fling.destination
        else:
            # jump there immediately
            log(f"{self} has no animator, so we'll just jump to the flung spot.")
            assert not occupant, f"{self} wanted to be flung to {fling.destination} but we have no animator and the tile is occupied by {occupant}!"
            self.on_fling_completed()

    def fling_destination_is_okay(self, fling, occupant):
        return False

    def on_fling_failed(self, fling):
        pass

    def on_fling_completed(self):
        assert self._fling
        position = self._fling.destination
        self._fling = None
        log(f"setting {self} position to {position}")
        self.position = position
        self.moving = False
        self.moving_to = None

    def interact(self, player):
        """Called when player interacts with this entity."""
        log(f'{player} interacted with {type(self)} at {self.position}')

    def on_blasted(self, bomb, position):
        log(f"{self} has been blasted!")
        if self.occupant:
            if self.position != None:
                position = self.position
            else:
                position = self.actor.position
            log(f"{self} occupant {self.occupant}, by transitivity, has also been blasted. (at position {position})")
            self.occupant.on_blasted(bomb, position)

    def on_frozen(self, bomb, position):
        log(f"{self} has been frozen!  I personally don't care.")
        if self.occupant:
            if self.position != None:
                position = self.position
            else:
                position = self.actor.position
            log(f"{self} occupant {self.occupant}, by transitivity, has also been frozen. (at position {position})")
            self.occupant.on_frozen(self, bomb, position)

    def set_freeze_timer(self, callback):
        if self.freeze_timer:
            self.freeze_timer.cancel()
        self.freeze_timer = Timer(f"{self} freeze timer", game.logics, freeze_timer_logics, callback)

    def on_stepped_on(self, occupier):
        self.occupant = occupier

    def remove(self):
        self.unqueue_for_tile()
        self.position = None

    def on_position_changed(self):
        pass

    def on_platform_animated(self, position):
        pass

    def on_platform_moved(self, position):
        pass

    def on_blasted(self, bomb, position):
        pass

    def on_pushed_into_something(self, other):
        pass

    def on_something_pushed_into_us(self, other):
        pass


class Claim(Entity):
    """
    A "claim" is a token owned by an entity.
    When the entity wants to animate from its
    old position to a new position,
    if the new position is unoccupied,
    the entity will put its claim on that coordinate:
        self.claim.position = coord
    (since Claim inherits from Entity, simply assigning
    its coordinate makes it occupy the tile)
    """
    def __init__(self, owner):
        self.owner = owner
        super().__init__(None)

    def __repr__(self):
        return f'Claim({self.owner!r})'

    def superceded(self):
        """
        Someone has superceded our claim!
        They are more important!
        Since our owner wanted to move here,
        and now we can't,
        register our desire to move there.
        """
        position = self.position
        log(f"{self} withdrawing claim on {position}!")
        assert level.tile_occupant[position] == self
        level.tile_occupant[position] = None
        self._position = None
        self.owner.queue_for_tile(position)



class Dam(Entity):
    floating = True
    is_platform = True

    def __init__(self, position):
        super().__init__(position)
        self.actor = scene.spawn_static(self.position, 'beaver-dam')
        level.on_dam_spawned(self)

    def on_blasted(self, bomb, position):
        super().on_blasted(bomb, position)
        self.actor.delete()
        pos = self.position
        self.position = None
        level.on_dam_destroyed(self)
        scene.spawn_particles(
            3,
            sprite_name='leaf1',
            position=pos,
            speed=2,
            zrange=(5, 20),
            vzrange=(5, 100),
            va=200,
            drag=0.5
        )
        scene.spawn_particles(
            2,
            sprite_name='leaf2',
            position=pos,
            speed=2,
            zrange=(5, 20),
            vzrange=(5, 100),
            va=100,
            drag=0.7
        )
        scene.spawn_particles(
            8,
            sprite_name='twig',
            position=pos,
            speed=0.8,
            zrange=(5, 10),
            vzrange=(15, 20),
            va=300,
            drag=0.8
        )


class Orientation(Enum):
    RIGHT = 0
    UP = 1
    LEFT = 2
    DOWN = 3

    def get_sprite(self):
        return ('right', 'up', 'left', 'down')[self.value]

    def to_vec(self):
        return orientation_to_position_delta[self]


class MovementAction(Enum):
    MOVE = 0
    EMBARK = 1
    DISEMBARK = 2


class PlayerAnimationState(IntEnum):
    STATIONARY = 0
    MOVING_ABORTABLE = 1
    MOVING_COMMITTED = 2


key_to_movement_delta = {
    key.UP:    Vec2D( 0, -1),
    key.DOWN:  Vec2D( 0, +1),
    key.LEFT:  Vec2D(-1,  0),
    key.RIGHT: Vec2D(+1,  0),
    }

key_to_opposite = {
    key.UP:    key.DOWN,
    key.DOWN:  key.UP,
    key.LEFT:  key.RIGHT,
    key.RIGHT: key.LEFT,
    }

orientation_to_position_delta = {
    Orientation.RIGHT: Vec2D(+1,  0),
    Orientation.UP:    Vec2D( 0, -1),
    Orientation.LEFT:  Vec2D(-1,  0),
    Orientation.DOWN:  Vec2D( 0, +1),
    }

key_to_orientation = {
    key.RIGHT: Orientation.RIGHT,
    key.UP:    Orientation.UP,
    key.LEFT:  Orientation.LEFT,
    key.DOWN:  Orientation.DOWN,
    }



class Player(Entity):
    MAX_BOMBS = 2
    dead = False

    def __init__(self, position):
        super().__init__(position)

        game.key_handler = self

        self.actor = scene.spawn_player(position)

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
        if position.y <= coords.TILES_H // 2:
            self.orientation = Orientation.DOWN
        elif position.x <= coords.TILES_W // 2:
            self.orientation = Orientation.RIGHT
        else:
            self.orientation = Orientation.LEFT

        self.animator = Animator(game.logics)
        self.halfway_timer = None
        self.moving = PlayerAnimationState.STATIONARY
        self.start_moving_timer = None
        self.queued_key = self.held_key = None

        self.bombs = []
        self.remote_control_bombs = []

        self.new_position = self.new_platform = None
        self.select_anim()

    def on_died(self):
        if not self.dead:
            self.dead = True
            pos = self.position
            for i, b in enumerate(reversed(self.bombs)):
                self.actor.detach(self.actor.attached[-1])
                scene.spawn_particles(
                    1,
                    sprite_name=b.sprite_name,
                    position=pos,
                    speed=4,
                    zrange=(80 + 20 * i,) * 2,
                    vzrange=(-20, 100),
                    va=300,
                    gravity=-400,
                )
            level.player_died()

    def on_blasted(self, bomb, position):
        if not self.dead:
            if self.standing_on is bomb:
                self.drown()
            else:
                self.actor.play('pc-smouldering')
                self.on_died()

    def drown(self):
        if not self.dead:
            position = self.position
            self.on_died()
            self.actor.delete()
            self.remove()
            DrowningPC(position)

    def push_bomb(self, bomb):
        """Pick up a bomb."""
        if len(self.bombs) == self.MAX_BOMBS:
            return False
        self.bombs.append(bomb)
        self.actor.attach(
            dynamite.scene.Bomb.sprites[bomb.sprite_name],
            x=0,
            y=60
        )
        for n, s in enumerate(reversed(self.actor.attached)):
            tween(s, tween='decelerate', duration=0.15, y=80 + 30 * n)
        self.select_anim()
        return True

    def pop_bomb(self):
        """Drop a bomb."""
        if not self.bombs:
            return None
        self.actor.detach(self.actor.attached[-1])
        for n, s in enumerate(reversed(self.actor.attached)):
            tween(s, tween='accelerate', duration=0.2, y=80 + 30 * n)
        bomb = self.bombs.pop()
        self.select_anim()
        return bomb

    def facing_pos(self):
        """Get the position the player is facing."""
        return self.position + self.orientation.to_vec()

    def on_platform_moved(self, platform):
        # if platform stops existing, it calls us with None
        # but! it's an exploding bomb! so we're about to die anyway.
        if platform is None:
            self.drown()
            return

        if self.moving == PlayerAnimationState.MOVING_ABORTABLE:
            self.new_position = platform.position
        else:
            assert self.moving in (PlayerAnimationState.MOVING_COMMITTED, PlayerAnimationState.STATIONARY)
            self.position = platform.position

    def on_platform_animated(self, position):
        if self.move_action is MovementAction.DISEMBARK:
            return
        if ((self.moving != PlayerAnimationState.STATIONARY)
            and self.animator):
            # FIXME: this updates the animator even if we're hopping off
            self.animator.end = position
        elif self.actor:
            self.actor.position = position

    def _animation_halfway(self):
        self.moving = PlayerAnimationState.MOVING_COMMITTED
        new_position = self.new_position
        if (not self.new_platform) or (self.new_platform.position == self.new_position):
            log(f"{self} everything's fine, just move to {self.new_position}.")
        else:
            # we're moving to a platform.  if it moved
            # out from underneath us, animate smoothly to
            # its new location.
            log(f"{self} platform moved out from underneath us from {self.new_position} to {self.new_platform.position}.  update position and reroute animation.")
            new_position = self.new_platform.position
            self.animator.reroute(self.new_platform.position)
        self.position = new_position
        self.new_position = self.new_platform = None

    def _animation_finished(self):
        log(f"{self} finished animating")
        self.moving = PlayerAnimationState.STATIONARY
        self.moving_to = None
        if self.queued_key:
            if self.held_key:
                assert self.held_key == self.queued_key, f"{key_repr(self.held_key)} != {key_repr(self.queued_key)} !!!"
            k = self.queued_key
            self.queued_key = None
            self.on_key(k)
        if self.held_key:
            self.on_key(self.held_key)
        self.select_anim()

    def select_anim(self):
        """Set the standard animations (standing/walk, holding?, direction)."""
        if self.dead:
            # Don't trample the death animations
            return
        animset = 'pc-holding' if self.bombs else 'pc'
        if self.moving is not PlayerAnimationState.STATIONARY:
            animset += '-walk'
        self.actor.play(f'{animset}-{self.orientation.get_sprite()}')

    def cancel_start_moving(self):
        if self.start_moving_timer:
            log(f"{self} canceling start_moving_timer")
            self.start_moving_timer.cancel()
            self.start_moving_timer = None
        else:
            log(f"{self} no start_moving_timer to cancel")

    def on_key_press(self, k):
        if key_to_movement_delta.get(k):
            log(f"{self} key press {key_repr(k)}")
            self.cancel_start_moving()
            self.held_key = k
            self.start_moving_timer = Timer("start moving " + key_repr(k), game.logics, player_movement_delay_logics, self._start_moving)

    def on_key_release(self, k):
        if k == self.held_key:
            log(f"{self} key release {key_repr(k)}")
            self.cancel_start_moving()
            self.held_key = None

    def can_move_to(self, new_position, navigability_mask=OCCUPIABLE_BY_PLAYER, verb="move to"):
        occupant = level.tile_occupant.get(new_position)
        if occupant and occupant != self.claim:
            if not occupant.is_platform:
                log(f"{self} can't {verb} space, it's occupied by {occupant} which isn't a platform.")
                return False
            if occupant.occupant:
                log(f"{self} can't {verb} space, it's occupied by {occupant}, which *is* a platform, but already has {occupant.occupant} on it.")
                return False
            if self.floating:
                log(f"{self} can't {verb} space, it's occupied by {occupant}, which *is* a platform, but we're floating.")
                return False
            log(f"{self} can {verb} space!  current occupant is {occupant}, but it's an unoccupied platform so it's cool.")
            return occupant

        tile = level.get(new_position)
        if not (tile.navigability & navigability_mask):
            log(f"{self} can't {verb} space!  it's not navigable, and current occupant is {occupant}.")
            return False
        log(f"{self} can {verb} space!  it's navigable, and current occupant is {occupant}.")
        return True

    thud = SafePlayer('thud.wav', streaming=False)
    splash = SafePlayer('splash.wav', streaming=False)

    def on_key(self, k):
        log(f"{self} on key {key_repr(k)}")

        # if k == key.ESCAPE:
        #     # pause / unpause
        #     if not game.paused:
        #         level.pause()
        #     return pyglet.event.EVENT_HANDLED

        if k == key.L:
            # log!  that's all L does.
            return

        if self.dead:
            log(f"{self} you're dead! you can't do {key_repr(k)} while you're dead!")
            return

        if k == key.E:
            target_obj = level.top_entity(level.player.facing_pos())
            if not target_obj:
                return
            target_obj.interact(level.player)
            return

        if k == key.T:
            # trigger remote control bomb
            if level.player.remote_control_bombs:
                bomb = level.player.remote_control_bombs.pop(0)
                log(f"{self} detonating bomb {bomb}")
                bomb.detonate()
            return

        if k == key.B:
            # if self.moving != PlayerAnimationState.STATIONARY:
            #     log("can't drop a bomb, player is moving.")
            #     return

            # drop bomb
            if not level.player.bombs:
                log("can't drop a bomb, player is out of bombs.")
                return
            bomb_position = level.player.facing_pos()
            result = self.can_move_to(bomb_position, OCCUPIABLE_BY_BOMB, "place bomb on")
            log(f"{self} can we drop a bomb at {bomb_position}?  {result}")
            if not result:
                return
            cls = level.player.pop_bomb()
            bomb = cls(bomb_position)
            if bomb.floating:
                snd = self.splash
            else:
                snd = self.thud

            clock.schedule_once(lambda dt: snd.play(), 0.3)
            level.player.remote_control_bombs.append(bomb)
            if result is not True:
                log(f"skipping bomb {bomb} across other bomb {result}")
                delta = bomb_position - level.player.position
                bomb.fling(delta)
            else:
                log(f"bomb {bomb} is fine where it is, not flinging/skipping.")
            return

        delta = key_to_movement_delta.get(k)
        if not delta:
            log(f"{self} on key {key_repr(k)}, isn't a movement key, ignoring")
            return

        desired_orientation = key_to_orientation[k]

        if self.moving == PlayerAnimationState.MOVING_COMMITTED:
            if self.orientation == desired_orientation:
                log(f"{self} on key {key_repr(k)}, we're committed to moving, ignoring keypress as we're already facing that way")
                self.queued_key = None
                return
            log(f"{self} on key {key_repr(k)}, we're committed to moving, when we finish we'll turn {desired_orientation!r}")
            self.queued_key = k
            return

        if self.moving == PlayerAnimationState.MOVING_ABORTABLE:
            if self.orientation == desired_orientation:
                # ignore
                log(f"{self} on key {key_repr(k)}, we're abortable-moving, you pressed a redundant key, ignoring")
                return
            self.queued_key = k
            # if we're quickly reversing direction,
            # abort movement if possible
            opposite_of_desired_orientation = key_to_orientation[key_to_opposite[k]]
            log(f"{self} on key {key_repr(k)}, we're abortable-moving")
            if self.orientation == opposite_of_desired_orientation:
                log(f"{self} on key {key_repr(k)}, aborting!")
                self.abort_movement()
            return

        if self.orientation != desired_orientation:
            log(f"{self} changing orientation to {desired_orientation!r}")
            self.orientation = desired_orientation
            self.select_anim()
            return

        new_position = self.position + delta

        stepping_onto_platform = None

        result = self.can_move_to(new_position)
        if not result:
            log(f"{self} can't move to {new_position} because {result}")
            return
        elif result is not True:
            stepping_onto_platform = result

        log(f"animating player, from {self.position} by {delta} to {new_position}")
        self.moving = PlayerAnimationState.MOVING_ABORTABLE
        self.moving_to = new_position
        self.new_position = new_position
        self.starting_position = self.actor.position
        self.select_anim()
        self.animator.animate(
            self.actor, 'position',
            new_position,
            player_movement_logics,
            self._animation_finished,
            self._animation_halfway)
        if (not self.standing_on) and stepping_onto_platform:
            log("{self} hopping up")
            stepping_onto_platform.occupant = self.claim
            self.new_platform = stepping_onto_platform
            tween(self.actor, 'hop_up', duration=typematic_interval, z=20)
            self.move_action = MovementAction.EMBARK
        elif self.standing_on and (not stepping_onto_platform):
            log("{self} hopping down")
            tween(self.actor, 'hop_down', duration=typematic_interval, z=0)
            self.move_action = MovementAction.DISEMBARK
        else:
            self.move_action = MovementAction.MOVE

    def _start_moving(self):
        assert self.held_key
        self.on_key(self.held_key)
        self.start_moving_timer = None

    def abort_movement(self):
        if self.moving != PlayerAnimationState.MOVING_ABORTABLE:
            return
        self.move_action = None
        self.moving = PlayerAnimationState.MOVING_COMMITTED
        starting_position = self.animator.position
        tween(self.actor, duration=0.1, z=20 if self.standing_on else 0)
        self.animator.animate(
            self.actor, 'position',
            self.starting_position,
            player_movement_logics / 3,
            self._animation_finished)
        self.moving_to = self.starting_position


def enumerate_outside_in(iterable):
    l = list(iterable)
    offset = 0
    while l:
        o = l.pop(0)
        yield offset, o
        if not l:
            break
        o = l.pop(-1)
        yield offset + len(l) + 1, o
        offset += 1


class BlastPattern:
    def __init__(self, strength, pattern):
        """
        The blast pattern is always outside-in.
        That ensures that when we push bombs,
        if there are two bombs in a row,
        the further-away one is processed first,
        which means it vacates its tile first,
        which means that its tile is available
        for the nearer one to move there.
        """
        self.strength = strength

        lines = [line.rstrip() for line in pattern.split("\n")]
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        center = None
        absolute_coordinates = []
        for y, line in enumerate_outside_in(lines):
            stripped_line = line.lstrip()
            x_offset = len(line) - len(stripped_line)
            for x, c in enumerate_outside_in(stripped_line):
                coordinate = Vec2D(x + x_offset, y)
                if c == "O":
                    # center
                    center = coordinate
                    # fall through, allow the center
                    # to be part of the blast pattern
                    # (in case you have a bomb stacked
                    # on top of another bomb)
                if not c.isspace():
                    absolute_coordinates.append(coordinate)
        assert center and absolute_coordinates
        self.coordinates = []
        for coordinate in absolute_coordinates:
            self.coordinates.append(coordinate - center)

    def __repr__(self):
        return f"BlastPattern({self.strength}, {self.coordinates})"

blast_pattern_1 = BlastPattern(2,
"""
 X
XOX
 X
""")

blast_pattern_2 = BlastPattern(3,
"""
  X
 XXX
XXOXX
 XXX
  X
""")


class FloatingPlatform(Entity):

    can_be_pushed_from_water_to_land = False

    def __init__(self, position):
        super().__init__(position)

        self.animator = Animator(game.logics)
        self.waiting_halfway = False
        self.make_actor()
        self.animate_if_on_moving_water()

    def move_with_animation(self, position, logics):
        log(f"{self} animating movement to {position}")
        self.new_position = position
        current_occupant = level.tile_occupant.get(position)
        if current_occupant:
            log(f"{self} wants to move to new_position, but it's occupied.  start moving anyway.")
            self.queue_for_tile(position)
        else:
            self.claim.position = position

        self.animator.animate(
            self.actor, 'position',
            position,
            logics,
            self._animation_finished,
            self._animation_halfway,
            self._animation_tick)
        self.moving = True
        self.moving_to = self.new_position

    def what_would_block_us_from_moving_to(self, position,
            okay_if_occupant_is_floating_away=True):
        tile = level.get(position)
        occupant = level.tile_occupant[position]
        prefix = f"{self} should we start floating to {position}? "
        if not tile.water:
            log(f"{prefix} no! it's not water.")
            return tile
        # okay, it's water.
        if not occupant:
            log(f"{prefix} yes! it's unoccupied water.")
            return None
        if occupant == self.claim:
            log(f"{prefix} yes!  we have claim to that space (occupant is {occupant}).")
            return None
        if not okay_if_occupant_is_floating_away:
            # it's occupied, and right now we don't care
            # whether or not the occupant is floating away.
            log(f"{prefix} no!  it's occupied by {occupant} and we don't care if it's moving away.")
            return occupant

        # if the occupant is floating away from us,
        # then they'll vacate by the time we get there,
        # so maybe it'll all be fine.
        assert occupant.position == position
        if not occupant.moving:
            log(f"{prefix} no!  it's occupied by {occupant} and the occupant isn't moving.")
            return occupant
        if (occupant.moving
            and occupant.moving_to == self.position):
            log(f"{prefix} no! it's occupied by {occupant} and the occupant is moving towards us.")
            return None
        log(f"{prefix} yes!  it's occupied by {occupant}, but the occupant is moving out, and not towards us.")
        return occupant

    def animate_if_on_moving_water(self):

        if self.standing_on:
            self.platform = self.floating = self.moving = False
            return

        tile = level.get(self.position)
        self.is_platform = self.floating = tile.water
        self.on_position_changed()

        log(f"{self} placed at {self.position}, tile is {tile}. is it moving water? {tile.moving_water}")

        if not tile.moving_water:
            return

        new_position = self.position + tile.current

        blocker = self.what_would_block_us_from_moving_to(new_position)
        if not blocker:
            self.move_with_animation(new_position, water_speed_logics)
            return

        # okay, we're being pushed into something.
        assert isinstance(blocker, (Entity, TileMeta)), f"blocker isn't an entity or map tile, it's {blocker}"
        self.on_pushed_into_something(blocker)
        if isinstance(blocker, Entity):
            blocker.on_something_pushed_into_us(self)
        return

    def on_pushed_into_something(self, other):
        log(f"{self} pushed into {other}.  we don't really care.")
        return False

    def on_something_pushed_into_us(self, other):
        log(f"{self} was pushed into by {other}.  we don't really care.")
        return False

    def _animation_halfway(self):
        current_occupant = level.tile_occupant[self.new_position]
        if current_occupant and current_occupant != self.claim:
            # we need to wait!
            log(f"{self} halfway... but we need to wait! occupied by {current_occupant}.")
            assert self.queued_tile == self.new_position, f"{self} queued_tile {self.queued_tile} != new_position {self.new_position} !!!"
            self.waiting_halfway = True
            self.animator.pause()
            return

        blocker = self.what_would_block_us_from_moving_to(self.new_position,
            okay_if_occupant_is_floating_away=False)
        if blocker:
            tile = level.get(self.new_position)
            log(f"{self} we can't continue floating to {self.new_position}! blocked by {blocker}.")
            self.on_pushed_into_something(blocker)
            if isinstance(blocker, Entity):
                blocker.on_something_pushed_into_us(self)
            return

        log(f"{self} halfway, proceeding.")
        self.waiting_halfway = False
        self.position = self.new_position
        if self.occupant:
            self.occupant.on_platform_moved(self)

    def on_tile_available(self, entity, position):
        assert self.queued_tile == position
        assert level.tile_occupant[position] == None
        log(f"{self} was queued for {position}, but it's now available! hooray!")
        self.claim.position = position
        self.unqueue_for_tile()
        if self.waiting_halfway:
            # we can proceed!
            self.animator.unpause()
            self._animation_halfway()

    def _animation_finished(self):
        log(f"{self} finished moving")
        self.moving = False
        self.moving_to = None
        self.animate_if_on_moving_water()

    def _animation_tick(self):
        if self.animator and self.occupant:
            self.occupant.on_platform_animated(self.animator.position)

    def on_blasted(self, bomb, position):
        super().on_blasted(bomb, position)
        if self._fling:
            # can't be double-flung! if we're already flinging somewhere
            # we ignore it.
            return
        self.pushed_by_explosion(position)

    def pushed_by_explosion(self, position):
        log(f"{self} (current position {self.position}) pushed by explosion from {position}! existing fling {self._fling}")
        if self._fling:
            return

        delta = self.position - position
        log(f"{self} delta {delta} floating {self.floating} can_be_pushed_from_water_to_land {self.can_be_pushed_from_water_to_land}")
        for delta in walk_vec2d_back_to_zero(delta):
            if not delta:
                break
            if self.floating:
                position = self.position + delta
                tile = level.get(position)
                log(f"{self} we're floating, tile at {position} is {tile}.  water? {tile.water}")
                if not (tile.water or self.can_be_pushed_from_water_to_land):
                    log(f"can't use delta {delta}, it would push us up from water to land")
                    continue
            break
        if delta:
            # if queued for tile, unqueue
            log(f"{self} explosion will fling us by {delta}")
            self.unqueue_for_tile()
            self.fling(delta)
        else:
            log(f"{self} explosion delta is {delta} so we're not flinging")

    def on_fling_completed(self):
        fling = self._fling
        assert fling

        # is our destination (what we flung to)
        # a platform?  our claim would be standing on something.
        standing_on = self.claim.standing_on
        log(f"{self} bomb fling completed.  did we land on a platform? {standing_on} {self.standing_on}")
        self.on_fling_failed(fling) # cleanup!

        super().on_fling_completed()
        log(f"just checking! {self} .fling is {self._fling}")
        if not standing_on:
            log(f"{self} was flung, and has now landed at {fling.destination}.")
            self.animate_if_on_moving_water()
        else:
            # re-fling!
            log(f"{self} was flung, but landed on {standing_on}, so we re-fling!")
            self.fling(fling.original_delta)

    def on_platform_animated(self, position):
        pass


class Log(FloatingPlatform):

    def __init__(self, position):
        log(f"{type(self).__name__} init, position is {position}")
        super().__init__(position)
        assert self.floating

    def make_actor(self):
        self.actor = scene.spawn_static(self.position, 'log')


class DrowningPC(Log):
    def make_actor(self):
        self.actor = scene.spawn_player(self.position, 'pc-drowning')


class Bomb(FloatingPlatform):
    blast_pattern = blast_pattern_1
    detonated = False
    can_be_pushed_from_water_to_land = True
    actor = None

    def __init__(self, position):
        self.current_sprite_name = None
        self.frozen = False

        super().__init__(position)

        self.actor.z = 50
        tween(self.actor, 'accelerate', duration=0.2, on_finished=self.on_position_changed, z=0)

    def make_actor(self):
        self.actor = scene.spawn_bomb(self.position, self.sprite_name)

    def on_position_changed(self):
        suffix = "-float" if self.floating else ""
        suffix += "-frozen" if self.frozen else ""
        if self.actor:
            sprite_name = f'{self.sprite_name}{suffix}'
            if self.current_sprite_name != sprite_name:
                log(f"{self} now playing {sprite_name}")
                self.actor.play(sprite_name)
                self.current_sprite_name = sprite_name

    def interact(self, player):
        """Allow the player to pick up the bomb.

        Bombs that cannot be taken will override this method.
        """
        if self.floating:
            return
        taken = player.push_bomb(type(self))
        if taken:
            if isinstance(player, Player):
                if self in player.remote_control_bombs:
                    player.remote_control_bombs.remove(self)
            self.actor.delete()
            self.remove()

    # def on_level_loaded(self):
    #     # when a bomb spawns on moving water,
    #     # if the space it wants to animate to is open,
    #     # it stakes its "claim" there.
    #     # but maybe next we spawn something on that space!
    #     # so:
    #     #   if our claim has a position set,
    #     #     and that position now has something
    #     #     on it besides our claim:
    #     #     withdraw our claim and queue for the tile.
    #     claim_position = self.claim.position
    #     if not claim_position:
    #         return
    #     occupant_at_claim = level.tile_occupant[claim_position]
    #     if occupant_at_claim != self.claim:
    #         log(f"{self} withdrawing claim after level loaded, {claim_position} occupied by {occupant_at_claim}")
    #         self.claim.superceded()

    def detonate(self):
        if self.detonated:
            return
        self.detonated = True
        if self._fling:
            assert self.position is None
            position = self.animator.position
            position = Vec2D(math.floor(position.x), math.floor(position.y))
        else:
            position = self.position

        log(f"{self} detonating at {position}!")

        if self.animator:
            self.animator.cancel()
        self.unqueue_for_tile()
        self.actor.scene.spawn_explosion(self.actor.position)
        self.detonation_effects()
        self.actor.delete()
        self.remove()  # Remove ourselves before processing on_blasted
        # t = Timer(f"bomb {self} detonation", game.logics, exploding_bomb_interval, self.remove)
        # log(f"WHAT THE HELL TIMER {t}")
        for delta in self.blast_pattern.coordinates:
            coordinate = position + delta
            e = level.tile_occupant[coordinate]
            if e:
                e.on_blasted(self, position)
        if self.occupant:
            self.occupant.on_blasted(self, position)

    def remove(self):
        log(self, "bomb has exploded, removing self.")
        self.position = None
        self.claim.position = None

    def on_blasted(self, bomb, position):
        # explicitly pass over FloatingPlatform.on_blasted
        super(FloatingPlatform, self).on_blasted(bomb, position)
        if bomb == self:
            return
        if self._fling:
            log(f"{self} can't be double-flung!  we have to detonate.")
            # can't be double-flung! if we're already flinging somewhere
            # we just detonate.
            self.detonate()
            return
        self.pushed_by_explosion(position)

    def fling_destination_is_okay(self, fling, occupant):
        if occupant.is_platform and not occupant.occupant:
            log(f"{self}: can we fling to {fling.destination}? it has {occupant} but we can stand there, so yes!")
            occupant.occupant = self.claim
            self.claim.standing_on = occupant
            return True

    def on_fling_failed(self, fling):
        # all this does is unset on_standing_on
        # so it's called from on_fling_completed too,
        # just to clean up.
        standing_on = self.standing_on
        if standing_on:
            standing_on.occupant = None
            standing_on = None

    explosion = SafePlayer('explosion2.wav', streaming=False)

    def detonation_effects(self):
        self.explosion.play()
        game_screen.screen_shake()



class TimedBomb(Bomb):
    sprite_name = 'timed-bomb'
    interval = timed_bomb_interval

    SPARK_COLOR = 0xff, 0xa9, 0x00

    def __init__(self, position, lit=True):
        super().__init__(position)

        self.start_time = game.logics.counter
        self.lit = False
        if lit:
            self.light_fuse()

    def light_fuse(self):
        if self.lit:
            return
        self.red_timer = Timer("bomb toggle red", game.logics, self.interval * 0.5, self.toggle_red)
        self.detonate_timer = Timer("bomb detonate", game.logics, self.interval, self.detonate)

        sx, sy = (20, 27) if self.floating else (18, 35)
        self.spark = self.actor.attach(
            dynamite.scene.Bomb.sprites['spark'],
            x=sx,
            y=sy,
        )
        self.spark.scale = 0.5
        self.spark.color = self.SPARK_COLOR
        self.t = 0
        clock.schedule(self.update_spark)
        self.lit = True

    def on_blasted(self, bomb, position):
        """If blasted, the fuse get lit!"""
        super().on_blasted(bomb, position)
        self.light_fuse()

    def interact(self, player):
        if not self.lit:
            taken = player.push_bomb(type(self))
            if taken:
                self.actor.delete()
                self.remove()

    def detonate(self):
        self.spark = None
        clock.unschedule(self.update_spark)
        super().detonate()

    def update_spark(self, dt):
        if not self.spark:
            return
        self.t += dt

        self.spark.scale = 0.5 + 0.1 * math.sin(self.t * 10)
        if not self.frozen:
            self.spark.rotation += 1.5 * 360 * dt

    def on_frozen(self, bomb, position):
        log(f"{self} has been frozen!  pause the countdowns.")
        self.set_freeze_timer(self.on_unfreeze)
        self.frozen = True
        if self.lit:
            self.red_timer.pause()
            self.detonate_timer.pause()
        self.on_position_changed()

    def on_unfreeze(self):
        log(f"{self} has unfrozen!  continue the countdowns.")
        self.frozen = False
        if self.lit:
            self.red_timer.unpause()
            self.detonate_timer.unpause()
        self.on_position_changed()

    def toggle_red(self):
        elapsed = game.logics.counter - self.start_time
        if self.actor.scene:
            self.actor.toggle_red()
            if elapsed < (timed_bomb_interval - logics_per_second):
                next = 0.4 * logics_per_second
            else:
                next = 0.1 * logics_per_second
            self.red_timer = Timer("bomb toggle red again", game.logics, next, self.toggle_red)


class FreezeBomb(TimedBomb):
    sprite_name = 'freeze-bomb'
    interval = freeze_detonation_interval

    SPARK_COLOR = 255, 255, 255

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def detonate(self):
        if self.detonated:
            return
        self.detonated = True

        self.spark = None
        clock.unschedule(self.update_spark)

        if self._fling:
            assert self.position is None
            position = self.animator.position
            position = Vec2D(math.floor(position.x), math.floor(position.y))
        else:
            position = self.position

        log(f"{self} freeze-detonating at {position}!")

        if self.animator:
            self.animator.cancel()
        self.unqueue_for_tile()
        self.actor.scene.spawn_explosion(self.actor.position, freeze=True)
        self.detonation_effects()

        self.actor.delete()
        self.remove()  # Remove ourselves before processing on_blasted
        # t = Timer(f"bomb {self} detonation", game.logics, exploding_bomb_interval, self.remove)
        # log(f"WHAT THE HELL TIMER {t}")
        for delta in self.blast_pattern.coordinates:
            coordinate = position + delta
            e = level.tile_occupant[coordinate]
            if e:
                e.on_frozen(self, position)

        if self.occupant:
            self.occupant.on_frozen(self, position)


class ContactBomb(Bomb):
    sprite_name = 'contact-bomb'
    frozen = False
    detonation_timer = None

    def on_blasted(self, bomb, position):
        # explicitly pass over FloatingPlatform.on_blasted
        super(FloatingPlatform, self).on_blasted(bomb, position)
        self.detonate_after_delay()

    def in_contact_with_entity(self, entity):
        if self.frozen:
            log(f"{self} contact bomb and {entity} are pushed together! but we're frozen right now!  so ignore it.  FOR NOW")
            return False
        log(f"{self} contact bomb and {entity} are pushed together! kaboom!")
        self.detonate_after_delay()
        return True

    def detonate_after_delay(self):
        if self.detonation_timer:
            return
        self.detonation_timer = Timer("ContactBomb detonation delay", game.logics, contact_bomb_detonation_interval, self.detonate)
        if self.frozen:
            self.detonation_timer.pause()

    def on_pushed_into_something(self, other):
        return self.in_contact_with_entity(other)

    def on_something_pushed_into_us(self, other):
        return self.in_contact_with_entity(other)

    def on_frozen(self, bomb, position):
        log(f"{self} has frozen!  desensitize to contact.")
        self.set_freeze_timer(self.on_unfreeze)
        if self.detonation_timer:
            self.detonation_timer.pause()
        self.frozen = True
        self.on_position_changed()

    def on_unfreeze(self):
        log(f"{self} has unfrozen!  become sensitive again.")
        self.frozen = False
        if self.detonation_timer:
            self.detonation_timer.unpause()
        self.animate_if_on_moving_water()
        self.on_position_changed()



class RemoteControlBomb(Bomb):
    sprite_name = 'remote-bomb'


class Scenery(Entity):
    def __init__(self, position, sprite):
        super().__init__(position)
        self.actor = scene.spawn_static(position, sprite)

    def remove(self, dt=None):
        super().remove()
        self.actor.delete()


class Dispenser(Scenery):
    """A dispenser for bombs."""

    def __init__(self, position, bomb_type):
        super().__init__(position, f'dispenser-{bomb_type.sprite_name}')
        self.bomb_type = bomb_type

    def interact(self, player):
        player.push_bomb(self.bomb_type)


class Bush(Scenery):
    def __init__(self, position):
        super().__init__(position, 'bush')

    def on_blasted(self, bomb, position):
        pos = self.position
        self.remove()
        scene.spawn_particles(
            10,
            sprite_name='leaf1',
            position=pos,
            speed=2,
            zrange=(5, 50),
            vzrange=(5, 100),
            va=200,
            drag=0.5
        )
        scene.spawn_particles(
            8,
            sprite_name='leaf2',
            position=pos,
            speed=2,
            zrange=(5, 50),
            vzrange=(5, 100),
            va=100,
            drag=0.7
        )


# We have to start with the window invisible in order to be able to set
# the icon, under some WMs
window = pyglet.window.Window(
    coords.WIDTH,
    coords.HEIGHT,
    caption=TITLE,
    visible=False,
)
window.set_icon(
    *(pyglet.resource.image(f'icons/dv-{sz}.png') for sz in (128, 64, 32))
)
window.set_visible(True)


game = None
game_screen = None
scene = None
level = None


def start_game_screen():
    global game_screen
    game_screen = GameScreen(window)
    game.unpause()

level_number = None
level_set = None

def start_game(_level_set, start_level=1):
    global level_number
    global level_set
    level_number = start_level - 1
    level_set = _level_set
    next_level()

def _next_level_filename():
    return level_set.format(number=level_number + 1)

def next_level():
    global level_number
    if level_number is None:
        sys.exit("You played your one level.  Now git!")
    level_number += 1
    start_level(level_set.format(number=level_number))

def start_level(filename):
    """Start the level with the given filename."""
    global game_screen
    if game_screen:
        game_screen.end()

    global game
    game = Game()

    global scene
    scene = dynamite.scene.Scene()

    global level
    level = Level()

    log(f"loading level {filename}")

    try:
        map = load_map(filename, globals())
    except pyglet.resource.ResourceNotFoundException:
        # end of level set! you win!
        level.game_won()
        return

    level.set_map(map)
    level.name = filename
    level.mtime = map.mtime

    # last-minute level fixups... it's complicated.
    # for entity in level.tile_occupant.values():
    #     if entity:
    #         entity.on_level_loaded()

    if not level.dams_remaining:
        sarcastic_rejoinder = "\n\nNo dams defined in level!  Uh, you win?\n\n"
        print(sarcastic_rejoinder)
        sys.exit(-1)

    scene.level_renderer = LevelRenderer(level)
    scene.flow = FlowParticles(level)

    title = map.metadata.get('title')
    if title:
        window.set_caption(f'{title} - {TITLE}')
    else:
        window.set_caption(TITLE)

    game.pause()
    IntroScreen(window, map, on_finished=start_game_screen)




def check_update_level(dt):
    """Check whether the level data has been changed."""
    d = Path(__file__).parent / 'levels'
    if (((d / level.name).stat().st_mtime != level.mtime)
        or ((d / "legend.txt").stat().st_mtime != level.legend_mtime)):
        reload_level()


def reload_level():
    """Reload the current level."""
    start_level(level.name)


def screenshot_path():
    root = Path.cwd()
    grabs = root / 'grabs'
    grabs.mkdir(exist_ok=True)
    day = (datetime.date.today() - datetime.date(2018, 10, 20)).days
    for n in itertools.count(1):
        path = grabs / f'day{day}-{n}.png'
        if not path.exists():
            return str(path)


def timer_callback(dt):
    if game:
        game.timer(dt)
    if scene:
        scene.flow.update(dt)


pyglet.clock.schedule_interval(timer_callback, callback_interval)

class GameScreen(Screen):
    SPRITES = [
        dynamite.scene.AnchoredImg('canyon-wall', anchor_x=25, anchor_y=25),
        dynamite.scene.AnchoredImg('bubble-win', anchor_x=0, anchor_y=0),
        dynamite.scene.AnchoredImg('bubble-death', anchor_x=353, anchor_y=0),
    ]

    def start(self):
        self.cam_offset = Vec2D(0, 0)
        self.cam_vel = Vec2D(0, 0)
        self.wall = pyglet.sprite.Sprite(
            self.sprites['canyon-wall'],
            x=0,
            y=self.window.height - 100,
        )
        self.create_hud()
        self.clock.schedule(self.steady_cam)

    def screen_shake(self):
        angle = random.uniform(0, math.tau)

        dist = 25
        vx = dist * math.sin(angle)
        vy = dist * math.cos(angle)
        self.cam_offset = Vec2D(vx, vy)

    def steady_cam(self, dt):
        dt = 0.05  # guarantee stable behaviour
        self.cam_offset += self.cam_vel * dt
        self.cam_vel -= self.cam_offset * 300 * dt
        self.cam_vel *= 0.1 ** dt
        self.cam_offset *= 0.01 ** dt

    def create_hud(self):
        board = pyglet.resource.image('board.png')
        self.board = pyglet.sprite.Sprite(
            board,
            x=10,
            y=self.window.height - 10 - board.height,
            batch=self.batch,
            group=pyglet.graphics.OrderedGroup(1),
        )
        self.hud_label = Label(
            self.hud_text(),
            x=board.width // 2 + 10,
            y=self.board.y + 11,
            font_name=BODY_FONT,
            font_size=20,
            anchor_x='center',
            anchor_y='bottom',
            color=(0, 0, 0, 255),
            batch=self.batch,
            group=pyglet.graphics.OrderedGroup(2)
        )

    def show_death_msg(self):
        self.display_big_text_and_wait("YOU DIED!")
        self.bubble = pyglet.sprite.Sprite(
            self.sprites['bubble-death'],
            x=self.window.width - 30,
            y=30,
            batch=self.batch,
        )
        self.bubble.visible = False
        self.clock.schedule_once(self._show_bubble, 0.5)

    def show_level_complete(self):
        game_screen.display_big_text_and_wait("LEVEL COMPLETE!")
        self.bubble = pyglet.sprite.Sprite(
            self.sprites['bubble-win'],
            x=30,
            y=30,
            batch=self.batch,
        )
        self.bubble.visible = False
        self.clock.schedule_once(self._show_bubble, 0.5)

    def _show_bubble(self, dt):
        self.bubble.visible = True
        self.bubble.scale = 0.1
        self.clock.animate(
            self.bubble,
            'bounce_end',
            duration=0.5,
            scale=1,
        )

    def display_big_text_and_wait(self, big_text, press_space="Press Space to continue"):
        self.complete_label = Label(
            big_text,
            x=window.width // 2,
            y=window.height - 200,
            font_name=BODY_FONT,
            font_size=40,
            anchor_x='center',
            anchor_y='center',
            color=(0, 0, 0, 255),
            batch=self.batch,
        )
        self.any_key_label = Label(
            press_space,
            x=window.width // 2,
            y=window.height - 300,
            font_name=BODY_FONT,
            font_size=15,
            anchor_x='center',
            anchor_y='center',
            color=IntroScreen.HIGHLIGHT_TEXT,
            batch=self.batch
        )

    def hud_text(self):
        plural = "" if (level.dams_remaining == 1) else "s"
        return f'{level.dams_remaining} dam{plural} remaining'

    def hide_hud(self):
        self.hud_label.delete()
        self.hud_label = None
        self.board.delete()
        self.board = None

    def handle_big_text_callback(self, name):
        callback = getattr(level, name, None)
        log(f"{self} CALLBACK for {name} is {callback}")
        if not callback:
            return None
        if self.complete_label:
            self.complete_label.delete()
            self.complete_label = None
        if self.any_key_label:
            self.any_key_label.delete()
            self.any_key_label = None
        setattr(level, name, None)
        return callback()

    def on_key_press(self, k, modifiers):
        if k == key.SPACE:
            log("Handling Space with big text")
            return self.handle_big_text_callback("on_space_pressed")

        if k == key.ESCAPE:
            log("GameScreen handle pause")
            if not game.paused:
                log("Pausing")
                level.pause()
            else:
                log("Handling esc with big text")
                self.handle_big_text_callback("on_esc_pressed")
            return pyglet.event.EVENT_HANDLED

        if k == key.Y:
            log("Handling Y with big text")
            return self.handle_big_text_callback("on_y_pressed")

        if k == key.F5:
            reload_level()
            return

        if k == key.F12:
            gl.glPixelTransferf(gl.GL_ALPHA_BIAS, 1.0)  # don't transfer alpha channel
            image = pyglet.image.ColorBufferImage(0, 0, window.width, window.height)
            image.save(screenshot_path())
            gl.glPixelTransferf(gl.GL_ALPHA_BIAS, 0.0)  # restore alpha channel transfer
            return
        return game.on_key_press(k, modifiers)

    def on_key_release(self, k, modifiers):
        return game.on_key_release(k, modifiers)

    def on_draw(self):
        gl.glClearColor(66 / 255, 125 / 255, 193 / 255, 0)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPushMatrix()

        x, y = self.cam_offset
        gl.glTranslatef(round(x), round(y), 0)
        window.clear()

        scene.flow.draw()
        self.wall.draw()

        scene.level_renderer.draw()

        if not (level and level.player):
            return

        scene.draw()
        gl.glPopMatrix()

        if self.hud_label:
            self.hud_label.text = self.hud_text()
        self.batch.draw()


def title_screen():
    # note: NOT AN F STRING
    # this is LAZILY COMPUTED when NUMBER changes
    level_set ='level{number}.txt'
    TitleScreen(
        window,
        on_finished=lambda: BackStoryScreen(window, on_finished=lambda: start_game(level_set))
    )

if len(sys.argv) > 1:
    try:
        level_number = int(sys.argv[-1])
    except ValueError:
        pass
    else:
        start_game('level{number}.txt', level_number)
else:
    title_screen()


ambient = None
def load_ambient():
    global ambient
    if ambient is None:
        ambient = SafePlayer('ambient.mp3', streaming=True)

def play_ambient(dt=0):
    global ambient
    if ambient is not None:
        ambient.play()

def stop_ambient():
    global ambient
    if ambient is not None:
        _ambient = ambient
        ambient = None
        _ambient.pause()
        del _ambient

load_ambient()
play_ambient()
pyglet.clock.schedule_interval(play_ambient, 150.752)


try:
    pyglet.app.run()
except AssertionError as e:
    log(f"\n{e}")
    raise e

# dump_log()
