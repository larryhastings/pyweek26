WIDTH = 800
HEIGHT = 600

# how big a tile is: 64 pixels wide x 40 pixels tall
TILE_W = 64
TILE_H = 40

TILES_W = WIDTH // TILE_W
TILES_H = HEIGHT // TILE_H - 2

OFFSET_X = (WIDTH - TILE_W * TILES_W + TILE_W) // 2
OFFSET_Y = HEIGHT + (HEIGHT - TILE_H * TILES_H - TILE_H) // 2 - 3 * TILE_H

def map_to_screen(pos):
    x, y = pos
    return x * TILE_W + OFFSET_X, OFFSET_Y - y * TILE_H
