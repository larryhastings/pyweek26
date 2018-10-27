#!/usr/bin/env python3

import os.path
from os.path import exists, basename
import sys

def banner(s):
    print(s.strip() + "\n")

def enter_prompt():
    try:
        input("[Press Enter to continue, or Ctrl-C to abort>")
    except KeyboardInterrupt:
        sys.exit(0)

banner("""
___________________________________

  Dynamite Valley AVBin Installer
___________________________________

This script will install AVBin on a computer running Linux.
AVBin is necessary for Dynamite Valley to play sound.
""")

if not sys.platform.startswith("linux"):
    banner("""
This computer isn't running Linux.  You'll have to install manually.
Press Enter to open a web browser at the AVBin download page.
""".strip())
    enter_prompt()

    import webbrowser
    webbrowser.open_new("https://avbin.github.io/AVbin/Download.html")
    sys.exit()


banner("""
Press Enter to begin installing.  You may be be asked for your password,
because we need to sudo to root in order to complete the installation.
""")
enter_prompt()

platform_bits = "64" if sys.maxsize > 2**32 else "32"

avbin_url = "https://github.com/downloads/AVbin/AVbin/install-avbin-linux-x86-" + platform_bits + "-v10"
avbin_filename = basename(avbin_url)
os.system("wget " + avbin_url)
os.system("sudo sh " + avbin_filename)

if not exists("/usr/lib/libavbin.so"):
    sys.exit("Sorry, couldn't install AVBin!")

print("AVBin should be installed now!")
