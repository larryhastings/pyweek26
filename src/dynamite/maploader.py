from collections import namedtuple
import os
import re

import pyglet.resource

from .vec2d import Vec2D
from .coords import TILES_W, TILES_H


Map = namedtuple('Map', 'name next width height tiles mtime legend_mtime metadata')

# list of strings, separated by spaces
required_level_metadata = "next"


class MapFormatError(Exception):
    """The map data was in a bad format."""


def _read_grid(lines):
    map_lines = []
    for lineno, line in lines:
        if not line:
            continue
        if line == 'Legend':
            break
        map_lines.append(line)
    else:
        raise MapFormatError("The map data must contain a legend.")
    return map_lines


def load_legend(filename, lines):
    legend = {}
    # print(f"lines is {lines}")
    for lineno, line in lines:
        line = line.strip()
        if not line:
            break
        try:
            sym, expr = line.split(' ', 1)
        except ValueError:
            raise MapFormatError(
                f'Invalid legend line {line!r} at {filename} line {lineno}.'
            ) from None
        legend[sym] = expr

    if not legend:
        raise MapFormatError(f"No legend items were found in {filename}.")

    return legend

def load_map(filename, globals_=globals()):
    """Load a map from a text file.

    The text file should have a 2D grid of symbols at the top,
    and a legend at the bottom.

    """

    def enumerated_text(s):
        return iter(enumerate(s.strip().splitlines(), start=1))

    legend_filename = "legend.txt"
    with pyglet.resource.file(legend_filename, 'rt') as f:
        legend_mtime = os.fstat(f.fileno()).st_mtime
        legend = load_legend(legend_filename, enumerated_text(f.read()))

    if not filename.endswith(".txt"):
        filename += ".txt"
    with pyglet.resource.file(filename, 'rt') as f:
        mtime = os.fstat(f.fileno()).st_mtime
        map_text = f.read()

    lines = enumerated_text(map_text)
    map_lines = _read_grid(lines)

    additional_legend = load_legend(filename, lines)
    legend.update(additional_legend)

    metadata = {}
    lastk = None
    for lineno, line in lines:
        mo = re.match(r'^(?::(\w+):)? +(.*)', line)
        if not mo:
            raise MapFormatError(f"Unexpected data at line {lineno}")

        k, v = mo.groups()
        if not k:
            if not lastk:
                raise MapFormatError(f"Found {v} with no key at line {lineno}")
            metadata[lastk] += f'\n{v}'
        else:
            if k in metadata:
                raise MapFormatError(
                    f"Duplicate metadata key {k} at line {lineno}"
                )
            metadata[k] = v
            lastk = k

    for s in required_level_metadata.split():
        if s not in metadata:
            raise MapFormatError(f"Required metadata key {s!r} not found")

    # the map is currently map[y][x].
    # now rotate map so x is first instead of y.
    # and index by tuple rather than nested list.
    # so that we get map[x, y]
    # (which is what tmx gives us)
    map_width = len(map_lines[0])
    map_height = len(map_lines)

    dims = (map_width, map_height)
    expected_dims = (TILES_W, TILES_H)
    if dims != expected_dims:
        raise MapFormatError(
            f"The dimensions of the map must be {expected_dims} (not {dims})."
        )

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
        name=filename.replace('.txt', ''),
        next=metadata['next'],
        width=map_width,
        height=map_height,
        tiles=new_map,
        mtime=mtime,
        legend_mtime=legend_mtime,
        metadata=metadata,
    )
