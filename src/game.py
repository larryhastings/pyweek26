#!/usr/bin/env python3
import os
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

from pyglet import gl
import pyglet.image
import pyglet.window.key as key
import pyglet.window.key
import pyglet.resource
from pyglet import clock

from dynamite import coords
from dynamite.coords import map_to_screen
from dynamite.particles import FlowParticles
from dynamite.level_renderer import LevelRenderer
import dynamite.scene
from dynamite.maploader import load_map
from dynamite.vec2d import Vec2D
from dynamite.animation import animate as tween
from dynamite.titles import TitleScreen, Screen, IntroScreen, BackStoryScreen

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

callback_interval = logic_interval


player_movement_logics = typematic_interval * logics_per_second
player_movement_delay_logics = typematic_start * logics_per_second

water_speed_logics = 1 * logics_per_second
explosion_push_logics = logics_per_second / 10
fling_movement_logics = logics_per_second / 10

srcdir = Path(__file__).parent
pyglet.resource.path = [
    'images',
    'levels',
]
pyglet.resource.reindex()
pyglet.resource.add_font('edo.ttf')

LevelRenderer.load()
FlowParticles.load()


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
    key.L: key.L,
    key.E: key.E,
    key.SPACE: key.SPACE,
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
    key.L: "L",
    key.SPACE: "Space",
    }
key_repr = _key_repr.get

OCCUPIABLE_BY_PLAYER = 1
OCCUPIABLE_BY_BOMB   = 2


class TileMeta(type):
    def __add__(self, ano):
        return self() + ano


class MapOOB:
    water = False
    moving_water = False
    spawn_item = None
    obj_factory = None
    navigability = 0


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
                o = tile.spawn_item(coord)
                if isinstance(o, Player):
                    if self.player:
                        sys.exit(f"Player set twice!  at {self.player.position} and {o.position}")
                    self.player = o

        if not self.player:
            raise Exception("No player position set!")

    def __init__(self):
        self.start = time.time()
        self.player = None

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


class Animator:
    def __init__(self, clock):
        """
        clock should be a Clock.
        """
        self.clock = clock
        self.timer = self.halfway_timer = None

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
        return self.start + ((self.end - self.start) * self.ratio)

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

    # we've been flung across the map!
    _fling = None

    # are we a floating object?
    floating = False

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
                log(f"level.tile_occupant[{old_position}] = None")
                level.tile_occupant[old_position] = None
                departed_tile = old_position
            elif self.standing_on == old_occupant:
                old_occupant.on_stepped_on(None)
                self.standing_on = None
            elif self.standing_on and (self.standing_on == new_occupant):
                # if what we're standing on moved to this new position,
                # guess what! the platform moved! we're not stepping off!
                pass
            elif self._fling:
                # we're being flung.  our old position was a mystery for the ages.
                # hopefully our final destination will be less so.
                pass
            # else:
            #     assert False, f"{self}: I don't understand how we used to be on {old_position}, occupant is {old_occupant} and self.standing_on is {self.standing_on}"

        if position is not None:
            if new_occupant and (new_occupant == self.claim):
                # moving to our claimed tile
                new_occupant = None
                # MILD HACK don't use descriptor to assign here
                # the claim will think it's departing the tile
                # and call on_tile_available() on the next queued guy
                self.claim._position = None
            if new_occupant == None:
                log(f"level.tile_occupant[{position}] = {self}")
                level.tile_occupant[position] = self
            elif new_occupant.is_platform:
                assert new_occupant.occupant in (None, self, self.claim), f"we can't step on {new_occupant}, it's occupied by {new_occupant.occupant}"
                log(f"{self} stepping onto existing tile occupant {new_occupant}")
                self.standing_on = new_occupant
                new_occupant.on_stepped_on(self)
            # else:
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
        for v in walk_vec2d_back_to_zero(delta):
            log(f"trying delta {v}")
            if not v:
                log(f"fling failed, we walked back to zero without finding any viable spot.")
                return self.on_fling_failed(fling)
            fling = Fling(self, delta, v)
            occupant = level.tile_occupant[fling.destination]
            if (not occupant) or (occupant is self.claim) or self.fling_destination_is_okay(fling, occupant):
                break
            log(f"tile wasn't okay, occupant is {occupant}")

        # fling is okay!
        log(f"{self} being flung to {fling.destination}!")
        self._fling = fling
        if self.animator:
            log(f"{self} being animated to new position.")
            self.claim.position = fling.destination
            self.animator.cancel()
            self.animator.animate(
                self.actor, 'position',
                fling.destination,
                fling_movement_logics,
                self.on_fling_completed)
            self.position = None
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
            self.occupant.on_blasted(self, position)

    def on_stepped_on(self, occupier):
        self.occupant = occupier

    def remove(self):
        self.unqueue_for_tile()
        self.position = None


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

    def on_platform_animated(self, position):
        pass

    def on_platform_moved(self, position):
        pass

    def on_blasted(self, bomb, position):
        # pass it on to our owner
        self.owner.on_blasted(bomb, position)



class Dam(Entity):
    floating = True
    is_platform = True

    def __init__(self, position):
        super().__init__(position)
        self.actor = scene.spawn_static(self.position, 'beaver-dam')

    def on_blasted(self, bomb, position):
        super().on_blasted(bomb, position)
        self.actor.delete()
        self.position = None


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


class PlayerAnimationState(Enum):
    INVALID = 0
    STATIONARY = 1
    MOVING_ABORTABLE = 2
    MOVING_COMMITTED = 3


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

    def __init__(self, position):
        super().__init__(position)
        log(f"{self} *** NEW PLAYER ***")

        game.key_handler = self

        self.actor = scene.spawn_player(position)
        self.dead = False

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

        self.actor.set_orientation(self.orientation)
        self.animator = Animator(game.logics)
        self.halfway_timer = None
        self.moving = PlayerAnimationState.STATIONARY
        self.start_moving_timer = None
        self.queued_key = self.held_key = None

        self.bombs = []

    def on_blasted(self, bomb, position):
        if self.dead:
            # FIXME: may have died by drowning, could play a
            # drowning-smouldering animation
            return
        self.actor.play('pc-smouldering')
        self.dead = True

    def push_bomb(self, bomb):
        """Pick up a bomb."""
        if len(self.bombs) == self.MAX_BOMBS:
            return
        self.bombs.append(bomb)
        self.actor.attach(
            dynamite.scene.Bomb.sprites[bomb.sprite_name],
            x=0,
            y=60
        )
        for n, s in enumerate(reversed(self.actor.attached)):
            tween(s, tween='decelerate', duration=0.15, y=80 + 30 * n)

    def pop_bomb(self):
        """Drop a bomb."""
        if not self.bombs:
            return None
        self.actor.detach(self.actor.attached[-1])
        for n, s in enumerate(reversed(self.actor.attached)):
            tween(s, tween='accelerate', duration=0.2, y=80 + 30 * n)
        return self.bombs.pop()

    def facing_pos(self):
        """Get the position the player is facing."""
        return self.position + self.orientation.to_vec()

    def on_platform_moved(self, platform):
        # if platform stops existing, it calls us with None
        # but! it's an exploding bomb! so we're about to die anyway.
        if platform is None:
            self.actor.play('pc-drowning')
            self.actor.z = 0
            self.dead = True
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
        self.position = self.new_position

    def _animation_finished(self):
        log("finished animating")
        self.moving = PlayerAnimationState.STATIONARY
        if self.queued_key:
            if self.held_key:
                assert self.held_key == self.queued_key, f"{key_repr(self.held_key)} != {key_repr(self.queued_key)} !!!"
            k = self.queued_key
            self.queued_key = None
            self.on_key(k)
        if self.held_key:
            self.on_key(self.held_key)

    def cancel_start_moving(self):
        if self.start_moving_timer:
            log("canceling start_moving_timer")
            self.start_moving_timer.cancel()
            self.start_moving_timer = None
        else:
            log("no start_moving_timer to cancel")

    def on_key_press(self, k):
        if key_to_movement_delta.get(k):
            log(f"key press {key_repr(k)}")
            self.cancel_start_moving()
            self.held_key = k
            self.start_moving_timer = Timer("start moving " + key_repr(k), game.logics, player_movement_delay_logics, self._start_moving)

    def on_key_release(self, k):
        if k == self.held_key:
            log(f"key release {key_repr(k)}")
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


    def on_key(self, k):
        log(f"{self} on key {key_repr(k)}")

        if k == key.ESCAPE:
            # pause / unpause
            game.paused = not game.paused
            return

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

        if k == key.B:
            if self.moving != PlayerAnimationState.STATIONARY:
                log("can't drop a bomb, player is moving.")
                return
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
            self.actor.set_orientation(desired_orientation)
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
        self.new_position = new_position
        self.starting_position = self.actor.position
        self.animator.animate(
            self.actor, 'position',
            new_position,
            player_movement_logics,
            self._animation_finished,
            self._animation_halfway)
        if (not self.standing_on) and stepping_onto_platform:
            stepping_onto_platform.occupant = self.claim
            tween(self.actor, 'hop_up', duration=typematic_interval, z=20)
            self.move_action = MovementAction.EMBARK
        elif self.standing_on and (not stepping_onto_platform):
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

        self.floating = level.get(position).water
        if self.floating:
            self.is_platform = True
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

    def animate_if_on_moving_water(self):
        if self.standing_on:
            return
        tile = level.get(self.position)
        self.moving = tile.moving_water
        log(f"{self} placed at {self.position}, tile is {tile} moving? {self.moving}")

        if not self.moving:
            return

        new_position = self.position + tile.current
        self.move_with_animation(new_position, water_speed_logics)

    def _animation_halfway(self):
        current_occupant = level.tile_occupant[self.new_position]
        if current_occupant and current_occupant != self.claim:
            # we need to wait!
            log(f"{self} halfway... but we need to wait! occupied by {current_occupant}.")
            assert self.queued_tile == self.new_position, f"{self} queued_tile {self.queued_tile} != new_position {self.new_position} !!!"
            self.waiting_halfway = True
            self.animator.pause()
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
        self.floating = level.get(self.position).water
        if not standing_on:
            log(f"{self} was flung, and has now landed at {fling.destination}.")
            self.animate_if_on_moving_water()
        else:
            # re-fling!
            log(f"{self} was flung, but landed on {standing_on}, so we re-fling!")
            self.fling(fling.original_delta)



class Log(FloatingPlatform):

    def __init__(self, position):
        log(f"Log init, position is {position}")
        super().__init__(position)
        assert self.floating

    def make_actor(self):
        self.actor = scene.spawn_static(self.position, 'log')


class Bomb(FloatingPlatform):
    blast_pattern = blast_pattern_1
    detonated = False
    can_be_pushed_from_water_to_land = True

    def __init__(self, position):
        super().__init__(position)

        self.actor.z = 50
        tween(self.actor, 'accelerate', duration=0.2, on_finished=self.on_bomb_land, z=0)

    def make_actor(self):
        self.actor = scene.spawn_bomb(self.position, self.sprite_name)

    def on_level_loaded(self):
        # when a bomb spawns on moving water,
        # if the space it wants to animate to is open,
        # it stakes its "claim" there.
        # but maybe next we spawn something on that space!
        # so:
        #   if our claim has a position set,
        #     and that position now has something
        #     on it besides our claim:
        #     withdraw our claim and queue for the tile.
        claim_position = self.claim.position
        if not claim_position:
            return
        occupant_at_claim = level.tile_occupant[claim_position]
        if occupant_at_claim != self.claim:
            log(f"{self} withdrawing claim after level loaded, {claim_position} occupied by {occupant_at_claim}")
            self.claim._position = None
            self.queue_for_tile(claim_position)

    def on_bomb_land(self):
        if self.floating:
            self.actor.play(f'{self.sprite_name}-float')

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
        self.actor.delete()
        # t = Timer(f"bomb {self} detonation", game.logics, exploding_bomb_interval, self.remove)
        # log(f"WHAT THE HELL TIMER {t}")
        for delta in self.blast_pattern.coordinates:
            coordinate = position + delta
            e = level.tile_occupant[coordinate]
            if e:
                e.on_blasted(self, position)
        if self.occupant:
            self.occupant.on_blasted(self, position)
        self.remove()

    def remove(self):
        print(f"{self} bomb has exploded, removing self.")
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



class TimedBomb(Bomb):
    sprite_name = 'timed-bomb'

    def __init__(self, position):
        super().__init__(position)

        # TODO convert these to our own timers
        # otherwise they'll still fire when we pause the game
        Timer("bomb toggle red", game.logics, timed_bomb_interval * 0.5, self.toggle_red)
        Timer("bomb detonate", game.logics, timed_bomb_interval, self.detonate)
        self.start_time = game.logics.counter

        sx, sy = (20, 27) if self.floating else (18, 35)
        self.spark = self.actor.attach(
            dynamite.scene.Bomb.sprites['spark'],
            x=sx,
            y=sy,
        )
        self.spark.scale = 0.5
        self.t = 0
        clock.schedule(self.update_spark)

    def detonate(self):
        self.spark = None
        clock.unschedule(self.update_spark)
        super().detonate()

    def update_spark(self, dt):
        if not self.spark:
            return
        self.t += dt

        self.spark.scale = 0.5 + 0.1 * math.sin(self.t * 10)
        self.spark.rotation += 1.5 * 360 * dt

    def toggle_red(self):
        elapsed = game.logics.counter - self.start_time
        if self.actor.scene:
            self.actor.toggle_red()
            if elapsed < (timed_bomb_interval - logics_per_second):
                next = 0.4 * logics_per_second
            else:
                next = 0.1 * logics_per_second
            Timer("bomb toggle red again", game.logics, next, self.toggle_red)


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
        self.remove()


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

    map = load_map(filename, globals())

    level.set_map(map)
    level.name = filename
    level.mtime = map.mtime

    # last-minute level fixups... it's complicated.
    for entity in level.tile_occupant.values():
        if entity:
            entity.on_level_loaded()

    scene.level_renderer = LevelRenderer(level)
    scene.flow = FlowParticles(level)

    title = map.metadata.get('title')
    if title:
        window.set_caption(f'{title} - {TITLE}')
    else:
        window.set_caption(TITLE)

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
    game.timer(dt)
    scene.flow.update(dt)


pyglet.clock.schedule_interval(timer_callback, callback_interval)

class GameScreen(Screen):
    def start(self):
        self.wall = pyglet.sprite.Sprite(
            pyglet.resource.image('canyon-wall.png'),
            x=0,
            y=self.window.height - 100
        )

    def on_key_press(self, k, modifiers):
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
        window.clear()

        scene.flow.draw()
        self.wall.draw()

        scene.level_renderer.draw()

        if not (level and level.player):
            return

        scene.draw()


if len(sys.argv) > 1:
    fname = sys.argv[-1]
    if not fname.startswith('-'):
        start_level(fname)
else:
    TitleScreen(
        window,
        on_finished=lambda: BackStoryScreen(window, on_finished=lambda: start_level('level1.txt'))
    )

try:
    pyglet.app.run()
except AssertionError as e:
    log(f"\n{e}")
    raise e

# dump_log()
