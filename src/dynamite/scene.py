import operator
import pyglet.resource
import pyglet.graphics
import pyglet.sprite

from .coords import map_to_screen


class Scene:
    def __init__(self):
        self.objects = set()
        self.batch = pyglet.graphics.Batch()

        Tree.load()
        Bomb.load()
        Player.load()

    def draw(self):
        self.batch.invalidate()
        self.batch.draw()

    def spawn_tree(self, position, sprite='fir-tree'):
        return Tree(self, position, sprite)

    def spawn_bomb(self, position, sprite='timed-bomb'):
        return Bomb(self, position, sprite)

    def spawn_player(self, position, sprite='pc-up'):
        return Player(self, position, sprite)



class Actor:
    @classmethod
    def load(cls):
        if hasattr(cls, 'sprites'):
            return
        cls.sprites = {}
        for spr in cls.SPRITES:
            s = cls.sprites[spr] = pyglet.resource.image(f'{spr}.png')
            s.anchor_x = s.width // 2
            s.anchor_y = 10

    def __init__(self, scene, position, sprite_name='default'):
        """Do not use this constructor - use methods of Scene."""
        x, y = map_to_screen(position)
        self.sprite = pyglet.sprite.Sprite(
            self.sprites[sprite_name],
            x, y,
            group=pyglet.graphics.OrderedGroup(-y),
            batch=scene.batch,
        )

        self._pos = position
        self.scene = scene
        self.scene.objects.add(self)

    def play(self, name):
        self.sprite.image = self.sprites[name]

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, v):
        x, y = map_to_screen(v)
        self._pos = v
        self.sprite.position = x, y
        self.sprite.group = pyglet.graphics.OrderedGroup(-y)

    def delete(self):
        self.scene.objects.remove(self)
        self.sprite.delete()


class Player(Actor):
    SPRITES = [
        'pc-up',
        'pc-down',
        'pc-left',
        'pc-right',
    ]

    def set_orientation(self, d):
        self.play(f'pc-{d.get_sprite()}')


class Bomb(Actor):
    SPRITES = [
        'timed-bomb',
        'freeze-bomb',
        'contact-bomb',
        'bomb-float-1',
        'bomb-float-2',
    ]


class Tree(Actor):
    SPRITES = [
        'fir-tree',
    ]
