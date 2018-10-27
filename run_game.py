#!/usr/bin/env python3
import sys

if sys.version_info < (3, 6):
    sys.exit("Sorry, Dynamite Valley requires Python 3.6 or newer.")

try:
    # suppress pygame printing its banner :p
    import builtins
    old_print = print
    def print(*a): pass
    builtins.print = print
    import pyglet
    import pygame
except ImportError:
    sys.exit("Can't run Dynamite Valley!  Please install both Pyglet and PyGame.")

print = old_print
builtins.print = old_print

import os.path

argv0dir = os.path.dirname(sys.argv[0])
srcdir = os.path.abspath(argv0dir + "/src")
sys.path.insert(0, srcdir)
os.chdir(srcdir)

try:
    import game
except ImportError:
    sys.exit("Couldn't run Dynamite Valley!  Not sure why, sorry.")

sys.exit(game.main(sys.argv[1:]))
