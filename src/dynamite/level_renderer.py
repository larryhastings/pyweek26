from itertools import product

import pyglet.resource
import pyglet.image
import pyglet.graphics

from .coords import map_to_screen, TILE_W, TILE_H
from .vec2d import Vec2D


class LevelRenderer:
    """System for rendering a tile map."""

    @classmethod
    def load(cls):
        cls.tiles = pyglet.image.ImageGrid(
            pyglet.resource.image('tilemap.png'),
            rows=8,
            columns=5,
        ).get_texture_sequence()

    tilemap = {
        'wwww': (0, 3),
        'wwwg': (2, 2),
        'wwgw': (2, 0),
        'wwgg': (2, 1),
        'wgww': (0, 0),
        'wggw': (1, 0),
        'wggg': (3, 1),
        'gwww': (0, 2),
        'gwwg': (1, 2),
        'gwgg': (3, 0),
        'ggww': (0, 1),
        'ggwg': (4, 0),
        'gggw': (4, 1),
        'gggg': (1, 1),
        'wgwg': (3, 5),
        'gwgw': (2, 5),
    }

    def __init__(self, level):
        self.level = level
        self.rebuild()

    def rebuild(self):
        """Rebuild the batch based on the current contents of the level."""
        batch = pyglet.graphics.Batch()
        sprites = []
        def q(x, y):
            if x < 0:
                x = 0
            elif x >= self.level.width:
                x = self.level.width - 1
            if y < 0:
                return 'w'
            elif y >= self.level.height:
                y = self.level.height - 1
            t = self.level.get(Vec2D(x, y))
            return 'w' if t.water else 'g'
        coords = product(
            range(-1, self.level.width + 1),
            range(-1, self.level.height + 1)
        )
        for x, y in coords:
            bitv = (
                q(x + 1, y) +
                q(x + 1, y - 1) +
                q(x, y - 1) +
                q(x, y)
            )
            screenx, screeny = map_to_screen(Vec2D(x, y))
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

    def draw(self):
        """Draw the level."""
        self.batch.draw()
