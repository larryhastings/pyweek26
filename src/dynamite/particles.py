import random
import pyglet.resource

from .coords import map_to_screen


class FlowParticles:
    """Particles that indicate the flow of water."""

    @classmethod
    def load(cls):
        cls.ripple = pyglet.resource.image('ripple.png')

    def __init__(self, level):
        self.level = level
        self.batch = pyglet.graphics.Batch()
        self.particles = []
        for _ in range(5):
            self.update(0.3)

    def update(self, dt):
        water_tiles = {}
        for pos in self.level.coords():
            t = self.level.map.get(pos)
            if t is None:
                water_tiles[pos] = (0, 0)
            elif t.water:
                water_tiles[pos] = t.current

        new_particles = []
        for p in self.particles:
            p.age += dt
            if p.age > 4:
                continue

            if p.age < 1:
                p.opacity = p.age * p.bright
            elif p.age > 3:
                p.opacity = (4 - p.age) * p.bright

            x, y = p.map_pos
            current = water_tiles.get((round(x), round(y)))
            if not current:
                continue
            curx, cury = current

            vx, vy = p.v

            frac = 0.5 ** dt
            invfrac = 1.0 - frac
            vx = frac * vx + invfrac * curx
            vy = frac * vy + invfrac * cury

            p.v = vx, vy
            x += vx * dt * 0.3
            y += vy * dt * 0.3
            p.map_pos = x, y
            p.position = map_to_screen(p.map_pos)
            new_particles.append(p)

        for (tx, ty), current in water_tiles.items():
            if random.uniform(0, 3) > dt:
                continue
            x = random.uniform(tx - 0.5, tx + 0.5)
            y = random.uniform(ty - 0.5, ty + 0.5)

            map_pos = x, y
            sx, sy = map_to_screen(map_pos)
            p = pyglet.sprite.Sprite(
                self.ripple,
                sx,
                sy,
                batch=self.batch
            )
            p.age = 0
            p.bright = random.uniform(128, 255)
            cx, cy = current
            p.v = (
                cx + random.uniform(-0.5, 0.5),
                cy + random.uniform(-0.5, 0.5)
            )
            p.opacity = 0
            p.scale = random.uniform(0.2, 0.3)
            p.map_pos = map_pos
            new_particles.append(p)
        self.particles = new_particles

    def draw(self):
        self.batch.draw()
