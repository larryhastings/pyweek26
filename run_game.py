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
import subprocess

argv0dir = os.path.dirname(sys.argv[0])
srcdir = os.path.abspath(argv0dir + "/src")
os.chdir(srcdir)

interpreter = sys.executable or "python3"
cmdline = [interpreter, "-O", "game.py"]
cmdline.extend(sys.argv[1:])
result = subprocess.run(cmdline)

sys.exit(result.returncode)
