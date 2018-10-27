import math
import random
import copy

from pyglet import gl
from pyglet import clock
import pyglet.resource
import pyglet.graphics
import pyglet.sprite

from .coords import map_to_screen
from .vec2d import Vec2D


class Scene:
    def __init__(self):
        self.objects = set()
        self.batch = pyglet.graphics.Batch()
        self.clock = clock

        Static.load()
        Bomb.load()
        Player.load()
        Explosion.load()
        Particle.load()

    def clear(self):
        self.objects.clear()
        self.batch = pyglet.graphics.Batch()

    def draw(self):
        self.batch.invalidate()
        self.batch.draw()

    def spawn_static(self, position, sprite):
        return Static(self, position, sprite)

    def spawn_bomb(self, position, sprite='timed-bomb'):
        return Bomb(self, position, sprite)

    def spawn_player(self, position, sprite='pc-up'):
        return Player(self, position, sprite)

    def spawn_explosion(self, position, freeze=False):
        Explosion(self, position, freeze=freeze)
        if freeze:
            self.spawn_particles(
                15,
                'snowflake',
                position,
                (10, 30),
                4,
                (50, 100),
                50,
                0.2,
                -50
            )

    def spawn_particles(self, num, sprite_name, position, zrange, speed, vzrange, va, drag=1.0, gravity=-100):
        for _ in range(num):
            # Choose a random angle anywhere in the circle
            angle = random.uniform(0, math.tau)
            # Choose a random radius using a controllable distribution
            radius = math.sqrt(random.uniform(0, 1))

            # Convert angle/radius to a cartesian vector
            vx = speed * radius * math.sin(angle)
            vy = speed * radius * math.cos(angle)
            z = random.uniform(*zrange)
            vz = random.uniform(*vzrange)
            if random.randint(0, 1) == 1:
                va = -va

            Particle(
                self,
                position,
                sprite_name,
                (vx, vy),
                z,
                vz,
                va,
                drag,
                gravity
            )


class AnchoredImg:
    """An image that can be loaded later."""
    def __init__(self, name, anchor_x='center', anchor_y='center'):
        self.name = self.image_filename = name
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y

    def _set_anchor(self, img):
        if self.anchor_x == 'center':
            img.anchor_x = img.width // 2
        else:
            img.anchor_x = self.anchor_x
        if self.anchor_y == 'center':
            img.anchor_y = img.height // 2
        else:
            img.anchor_y = self.anchor_y

    def load(self):
        img = pyglet.resource.image(f'{self.image_filename}.png')
        img = copy.copy(img)  # resources are cached - get a unique copy
        self._set_anchor(img)
        return img


class ImageSequence(AnchoredImg):
    """An animation that can be loaded later."""
    def __init__(
            self,
            name,
            frames,
            delay=0.1,
            anchor_x='center',
            anchor_y='center',
            loop=False,
            flip_x_from=None):
        super().__init__(name, anchor_x, anchor_y)
        self.frames = frames
        self.delay = delay
        self.loop = loop
        self.flip_x = bool(flip_x_from)
        if self.flip_x:
            self.image_filename = flip_x_from

    def load(self):
        img = pyglet.resource.image(f'{self.image_filename}.png')
        grid = pyglet.image.ImageGrid(
            img,
            rows=1,
            columns=self.frames
        )

        images = list(grid)
        for img in images:
            self._set_anchor(img)

        anim = pyglet.image.Animation.from_image_sequence(
            images,
            self.delay,
            loop=self.loop
        )
        if self.flip_x:
            anim = anim.get_transform(flip_x=True)
        return anim


class ActorGroup(pyglet.graphics.OrderedGroup):
    def __hash__(self):
        return id(self)

    def __eq__(self, ano):
        return self is ano


class AttachmentGroup(pyglet.graphics.Group):
    def __init__(self, obj, parent):
        super().__init__(parent)
        self.obj = obj

    def set_state(self):
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPushMatrix()
        x, y = self.obj.position
        gl.glTranslatef(x, y, 0)

    def unset_state(self):
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPopMatrix()

    def __lt__(self, ano):
        return False


class Actor:
    DEFAULT_Z = 0

    @classmethod
    def load(cls):
        if hasattr(cls, 'sprites'):
            return
        cls.sprites = {}
        for spr in cls.SPRITES:
            if isinstance(spr, AnchoredImg):
                s = cls.sprites[spr.name] = spr.load()
            else:
                s = cls.sprites[spr] = pyglet.resource.image(f'{spr}.png')
                s.anchor_x = s.width // 2
                s.anchor_y = 10

    def __init__(self, scene, position, sprite_name='default'):
        """Do not use this constructor - use methods of Scene."""
        self._pos = position
        self._z = self.DEFAULT_Z

        self.group = ActorGroup(self.z_order())

        x, y = map_to_screen(position)
        self.sprite = pyglet.sprite.Sprite(
            self.sprites[sprite_name],
            x, y,
            group=pyglet.graphics.OrderedGroup(0, self.group),
            batch=scene.batch,
        )
        self.attach_group = AttachmentGroup(self.sprite, self.group)
        self.anim = sprite_name

        self.scene = scene
        self.scene.objects.add(self)
        self.attached = []

    def z_order(self):
        return (self._pos[1], self._z)

    def play(self, name):
        if not self.scene:
            return
        if self.anim != name:
            self.sprite.image = self.sprites[name]
            self.anim = name

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, v):
        x, y = map_to_screen(v)
        self._pos = v
        if not self.scene:
            return
        self.sprite.position = x, y + self._z
        self.group.order = self.z_order()

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, v):
        self._z = v
        self.position = self._pos  # trigger sprite update

    def delete(self):
        if not self.scene:
            return
        self.scene.objects.remove(self)
        self.sprite.delete()
        for spr in self.attached:
            spr.delete()
        self.scene = None

    def attach(self, img, x, y):
        """Attach another sprite on top of this."""
        sprite = pyglet.sprite.Sprite(
            img,
            x=x,
            y=y,
            group=self.attach_group,
            batch=self.sprite.batch,
        )
        self.attached.append(sprite)
        return sprite

    def detach(self, sprite):
        self.attached.remove(sprite)
        sprite.delete()



class Player(Actor):
    def walk(name, **kwargs):
        defaults = dict(
            anchor_y=23,
            frames=8,
            delay=0.05,
            loop=True,
        )
        return ImageSequence(
            name,
            **{**defaults, **kwargs}
        )

    DEFAULT_Z = 1
    SPRITES = [
        'pc-up',
        'pc-down',
        'pc-left',
        'pc-right',
        walk('pc-walk-up', anchor_y=19),
        walk('pc-walk-down', anchor_y=19),
        walk('pc-walk-right'),
        walk('pc-walk-left', flip_x_from='pc-walk-right'),
        'pc-holding-up',
        'pc-holding-down',
        'pc-holding-left',
        'pc-holding-right',
        walk('pc-holding-walk-up', anchor_y=19),
        walk('pc-holding-walk-down', anchor_y=19),
        walk('pc-holding-walk-right'),
        walk('pc-holding-walk-left', flip_x_from='pc-holding-walk-right'),
        'pc-frozen',
        'pc-frozen-floating',
        ImageSequence(
            'pc-smouldering',
            anchor_y=10,
            frames=3,
            delay=0.2,
            loop=True,
        ),
        ImageSequence(
            'pc-drowning',
            anchor_y=16,
            frames=2,
            delay=0.3,
            loop=True,
        ),
    ]
    del walk

    def set_orientation(self, d):
        self.play(f'pc-{d.get_sprite()}')


class Bomb(Actor):
    def floating(name, **kwargs):
        defaults = dict(
            frames=2,
            delay=1.1,
            anchor_x='center',
            anchor_y=14,
            loop=True,
        )
        return ImageSequence(
            name,
            **{
                **defaults,
                **kwargs,
            }
        )
    SPRITES = [
        AnchoredImg('timed-bomb', anchor_x=18, anchor_y=10),
        AnchoredImg('timed-bomb-red', anchor_x=18, anchor_y=10),
        AnchoredImg('timed-bomb-frozen', anchor_x=18, anchor_y=10),
        AnchoredImg('freeze-bomb', anchor_x=18, anchor_y=10),
        AnchoredImg('freeze-bomb-red', anchor_x=18, anchor_y=10),
        AnchoredImg('freeze-bomb-frozen', anchor_x=18, anchor_y=10),
        'contact-bomb',
        'contact-bomb-frozen',
        floating('contact-bomb-float', anchor_y=18),
        floating('contact-bomb-float-frozen', anchor_y=18),
        floating('timed-bomb-float'),
        floating('timed-bomb-float-red'),
        floating('timed-bomb-float-frozen'),
        floating('freeze-bomb-float'),
        floating('freeze-bomb-float-red'),
        floating('freeze-bomb-float-frozen'),
        AnchoredImg('spark'),
        'remote-bomb',
        'remote-bomb-frozen',
        floating('remote-bomb-float'),
        floating('remote-bomb-float-frozen'),
    ]
    del floating
    red = False

    def play(self, name):
        if not self.scene:
            return

        was_frozen = self.anim.endswith('-frozen')
        super().play(name)
        now_frozen = name.endswith('-frozen')
        if was_frozen and not now_frozen:
            self.scene.clock.unschedule(self.eject_snowflake)
        elif not was_frozen and now_frozen:
            self.scene.clock.schedule_interval(self.eject_snowflake, 0.2)

    def eject_snowflake(self, dt):
        if random.randint(0, 2):
            return
        self.scene.spawn_particles(
            1,
            'snowflake',
            self.position,
            (20, 30),
            1,
            (30, 40),
            50,
            0.2,
            -50
        )

    def delete(self):
        if not self.scene:
            return
        self.scene.clock.unschedule(self.eject_snowflake)
        super().delete()

    def toggle_red(self):
        """Flip the bomb sprite to/from red."""
        if self.red:
            img = self.sprites[self.anim]
        else:
            img = self.sprites[f'{self.anim}-red']

        # There is no method to replace an animation in a sprite, keeping
        # the current frame, so do this using the internals of the Sprite
        # class - see
        # https://bitbucket.org/pyglet/pyglet/src/de3608deb882c0719f231880ecb07f7d4bb58cb6/pyglet/sprite.py#lines-356
        if isinstance(img, pyglet.image.Animation):
            self.sprite._animation = img
            frame = self.sprite._frame_index
            self.sprite._set_texture(img.frames[frame].image.get_texture())
        else:
            self.sprite.image = img

        self.red = not self.red


class Explosion(Actor):
    SPRITES = [
        ImageSequence(
            'explosion',
            frames=9,
            delay=0.02,
            anchor_x=53,
            anchor_y=39,
        ),
        ImageSequence(
            'explosion-freeze',
            frames=9,
            delay=0.02,
            anchor_x=53,
            anchor_y=39,
        ),
    ]
    def __init__(self, scene, position, freeze=False):
        sprite = 'explosion-freeze' if freeze else 'explosion'
        super().__init__(scene, position, sprite)
        self.sprite.on_animation_end = self.delete
        self.sprite.scale = 2.0


class Static(Actor):
    """All static objects can go here."""
    SPRITES = [
        'fir-tree',
        'fir-tree-small',
        'bush',
        'beaver',
        'beaver-left',
        'beaver-right',
        AnchoredImg('beaver-dam', anchor_y=20),
        'log',
        AnchoredImg('dispenser-contact-bomb', anchor_y=30),
        AnchoredImg('dispenser-timed-bomb', anchor_y=30),
        AnchoredImg('dispenser-freeze-bomb', anchor_y=30),
        AnchoredImg('dispenser-remote-bomb', anchor_y=30),
        'bullrush',
        'rock',
    ]


class Particle(Actor):
    """3D-ish particle effects."""
    SPRITES = [
        AnchoredImg('timed-bomb', anchor_x=21, anchor_y=21),
        AnchoredImg('freeze-bomb', anchor_x=21, anchor_y=21),
        AnchoredImg('contact-bomb', anchor_x=24, anchor_y=21),
        AnchoredImg('leaf1', anchor_y=20),
        'leaf2',
        'twig',
        'snowflake',
    ]

    def __init__(
            self,
            scene,
            position,
            sprite_name,
            vxy,
            z,
            vz,
            va,
            drag=1.0,
            gravity=-100):
        super().__init__(scene, position, sprite_name)
        self.vxy = Vec2D(vxy)
        self.sprite.rotation = random.randrange(360)
        self.z = z
        self.vz = vz
        self.va = va
        self.drag = drag
        self.gravity = gravity
        self.scene.clock.schedule(self.update)

    def update(self, dt):
        self.vz = self.vz * self.drag ** dt + self.gravity * dt
        self.z += self.vz * dt

        if self.z < 0:
            if 'bomb' in self.anim:
                self.scene.spawn_explosion(
                    self.position,
                    'freeze' in self.anim
                )
            self.delete()
            return

        self.vxy *= self.drag ** dt
        self.position += self.vxy * dt
        self.sprite.rotation += self.va * dt

    def delete(self):
        self.scene.clock.unschedule(self.update)
        super().delete()
