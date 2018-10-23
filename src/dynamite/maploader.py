from collections import namedtuple

import pyglet.resource

from .vec2d import Vec2D


Map = namedtuple('Map', 'width height tiles')

map_legend = {}


map_text = """
...v<<<.......................
..#v##^.......................
.##v##^.......................
.#.>>>^.......................
.##.##X.......................
.##.##^.......................
.S#.##^##.....................
.##.T###......................
..............................
"""
# .S#.##^.......................
# .S###########################.


class MapFormatError(Exception):
    """The map data was in a bad format."""


def load_map(filename, globals_=globals()):
    """Load a map from a text file.

    The text file should have a 2D grid of symbols at the top,
    and a legend at the bottom.

    """
    with pyglet.resource.file(filename, 'r') as f:
        map_text = f.read()

    lines = iter(enumerate(map_text.strip().splitlines(), start=1))

    map_lines = []
    for lineno, line in lines:
        if not line:
            continue
        if line == 'Legend':
            break
        map_lines.append(line)
    else:
        raise MapFormatError("The map data must contain a legend.")


    legend = {}
    for lineno, line in lines:
        try:
            sym, expr = line.split(' ', 1)
        except ValueError:
            raise MapFormatError(
                f'Invalid legend line {line!r} at {lineno}'
            ) from None
        legend[sym] = expr

    if not legend:
        raise MapFormatError("No legend items were found.")

    # the map is currently map[y][x].
    # now rotate map so x is first instead of y.
    # and index by tuple rather than nested list.
    # so that we get map[x, y]
    # (which is what tmx gives us)
    map_width = len(map_lines[0])
    map_height = len(map_lines)
    if map_width == 0:
        raise MapFormatError("The width of the map may not be 0.")
    if map_height == 0:
        raise MapFormatError("The height of the map may not be 0.")

    for lineno, ln in enumerate(map_lines[1:], start=2):
        if len(ln) != map_width:
            raise MapFormatError(
                f"The map data was not rectangular (expected "
                f"{map_width} columns at {lineno}, found {len(ln)})."
            )

    new_map = {}
    for y, line in enumerate(map_lines):
        for x, tile in enumerate(line):
            try:
                exp = legend[tile]
            except KeyError:
                raise MapFormatError(
                    f"The symbol {tile!r} does not appear in the legend."
                ) from None
            new_map[Vec2D(x, y)] = eval(exp, globals_)

    return Map(
        width=map_width,
        height=map_height,
        tiles=new_map
    )
