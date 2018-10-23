import pyglet.resource
import pyglet.image
import pyglet.graphics

from .coords import map_to_screen
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

    def __init__(self, level):
        self.level = level
        self.rebuild()

    def rebuild(self):
        """Rebuild the batch based on the current contents of the level."""
        batch = pyglet.graphics.Batch()
        sprites = []
        def q(x, y):
            t = self.level.get(Vec2D(x, y))
            return not t.water
        for x, y in self.level.coords():
            bitv = (
                q(x, y) |
                q(x, y - 1) << 1 |
                q(x + 1, y - 1) << 2 |
                q(x + 1, y) << 3
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
