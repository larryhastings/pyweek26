import operator
from itertools import chain

from pyglet import gl
import pyglet.resource
import pyglet.graphics
import pyglet.sprite

from .coords import map_to_screen


class Scene:
    def __init__(self):
        self.objects = set()
        self.batch = pyglet.graphics.Batch()

        Static.load()
        Bomb.load()
        Player.load()
        Explosion.load()

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

    def spawn_explosion(self, position):
        Explosion(self, position)



class AnchoredImg:
    """An image that can be loaded later."""
    def __init__(self, name, anchor_x='center', anchor_y='center'):
        self.name = name
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
        img = pyglet.resource.image(f'{self.name}.png')
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
            loop=False):
        super().__init__(name, anchor_x, anchor_y)
        self.frames = frames
        self.delay = delay
        self.loop = loop

    def load(self):
        img = pyglet.resource.image(f'{self.name}.png')
        grid = pyglet.image.ImageGrid(
            img,
            rows=1,
            columns=self.frames
        )

        images = list(grid)
        for img in images:
            self._set_anchor(img)

        return pyglet.image.Animation.from_image_sequence(
            images,
            self.delay,
            loop=self.loop
        )


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
    DEFAULT_Z = 1
    SPRITES = [
        'pc-up',
        'pc-down',
        'pc-left',
        'pc-right',
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

    def set_orientation(self, d):
        self.play(f'pc-{d.get_sprite()}')


class Bomb(Actor):
    SPRITES = [
        'timed-bomb',
        'timed-bomb-red',
        'freeze-bomb',
        'contact-bomb',
        ImageSequence(
            'contact-bomb-float',
            frames=2,
            delay=1.1,
            anchor_x='center',
            anchor_y=18,
            loop=True,
        ),
        ImageSequence(
            'timed-bomb-float',
            frames=2,
            delay=1.1,
            anchor_x='center',
            anchor_y=14,
            loop=True,
        ),
        ImageSequence(
            'timed-bomb-float-red',
            frames=2,
            delay=1.1,
            anchor_x='center',
            anchor_y=14,
            loop=True,
        ),
        AnchoredImg('spark'),
    ]
    red = False

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
    ]
    def __init__(self, scene, position):
        super().__init__(scene, position, 'explosion')
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
        'bullrush',
        'rock',
    ]
