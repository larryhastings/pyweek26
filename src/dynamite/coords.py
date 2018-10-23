WIDTH = 800
HEIGHT = 600

# how big a tile is: 64 pixels wide x 40 pixels tall
TILE_W = 64
TILE_H = 40

TILES_W = WIDTH // TILE_W
TILES_H = HEIGHT // TILE_H


def map_to_screen(pos):
    x, y = pos
    return x * TILE_W + 100, 600 - 100 - y * TILE_H
