Dynamite Valley
===============

Copyright 2018 Daniel Pope and Larry Hastings.

It's fall, and that means it's blasting season!

The beavers here in Dynamite Valley Park have been
working overtime, making dams!  If I've told you
once, Ranger Jim, I've told you a thousand times--
now get out there and blast those consarned dams!

Guide Ranger Jim around a series of levels infested
with beaver dams damming up the waters of Dynamite
Valley Park.


Dynamite Valley is an exciting action game written by Daniel Pope and Larry Hastings for the "PyWeek 26" programming competition in October 2018.  This guide will explain to you everything you need to know to play Dynamite Valley.

We sincerely hope you have fun playing!  Now get out there and wipe out those dams!


The Basics
----------

You play as Ranger Jim, a park ranger at Dynamite Valley Park.  It's fall, and that means beavers have built dams all over the park!  Your job: remove the dams!  With explosives!

Every level has a number of "dams" floating in the water.  Ranger Jim has to destroy all the dams to advance to the next level.  If you complete all the levels, you win!


The "Dynamite Valley" Guarantee
-------------------------------

Both Dan and I played through the final version of the game, version 1.0.2.  Every level is winnable!  We guarantee it!

Note that on some levels you can put yourself into a situation where the level is no longer winnable.  For example, on some levels you only have a limited supply of bombs, and if you misuse them the level may no longer be winnable.  If you think that's happened, you should start the level over.

Also, the first zip file release of "Dynamite Valley" had a game-breaking bug.  We guarantee that version *isn't* winnable!  We only guarantee versions 1.0.1 and newer are winnable.


Starting The Game
-----------------

Dynamite Valley requires Python 3.6 or higher.

Check the requirements.txt for what you'll need.
Dynamite Valley needs both PyGame and Pyglet.

You might be able to install all Dynamite Valley's
requirements automatically by running this:

    % sudo pip3 install -r requirements.txt

Your mileage may vary!

We recommend running Dynamite Valley with
"python3 -O".  Pyglet's Open GL support occasionally,
if rarely, throws assertion failures.  If you use
the provided launcher `run_game.py` we do this for you.


Once you start the game, at any time during the title sequence you can press one of three keys to start your game:

T - Start the tutorial (recommended!).
N - Start a new game.
Space - Play the game starting at the last level you played.

Every time you start playing a level, the game remembers that, and if you exit the game and restart, pressing Space will take you straight to that level.  (It won't remember where you were, though--it'll just reload the level from scratch.)

Keyboard Controls
-----------------

In the game, you control Ranger Jim, a park ranger working in "Dynamite Valley".

"Dynamite Valley" supports the following keyboard commands in-game:

Up Down Left Right - move Ranger Jim, or change which direction he is facing
W A S D - redundant movement controls
E - interact with the object Ranger Jim is facing, like take a bomb from a dispenser, or pick up an inert bomb from the ground
B - drop a bomb, onto the spot where Ranger Jim is facing
T - trigger a Remote Control Bomb
Escape - pause game, bringing up the Pause Menu
F5 - restart level
F12 - take screenshot

Ranger Jim can pick up up to two bombs at a time.  When he drops a bomb, he drops the bottom bomb from the stack.  That's always the most recent bomb he picked up.

Dynamite Valley doesn't support joysticks or the mouse.

Bombs And Explosions
--------------------

Ranger Jim does his work with bombs.  As we all know, bombs "detonate", turning them into explosions which "blast" nearby objects.  Specifically, exploding bombs in Dynamite Valley "blast" their four nearest neighbors (up/down/left/right).  Bombs on land can still blast objects floating in the water, and bombs in the water can still blast objects on land.

Bombs that Ranger Jim drops are automatically armed.  Ranger Jim can't pick up a bomb that's been armed.

There are four types of bombs in the game:

* Timed Bombs are the most frequently-seen type of bomb.  They look like the classic movie bomb: a black circle with a small black cylinder near the top, and a fuse.  They detonate in 5 seconds after being dropped.  When "blasted", Timed Bombs are "flung" one space away.

* Contact Bombs look like black spheres with little round nubs poking out in all directions.  They automatically detonate when they're pushed into something, or if they're blasted by another bomb.

* Remote Control Bombs look like Timed Bombs but with a red ring around the small cylinder at the top.  You can detonate an RC Bomb with the "T"rigger key.  RC Bombs detonate in the order you dropped them--if you drop five bombs, you have to press "T" five times to trigger them all.  Remote Control Bombs that are blasted are "flung" like Timed Bombs.

* Freeze Bombs look like Timed Bombs, except they're white and they have light blue snowflakes drawn on the side.  They detonate in 2 seconds after being dropped.  Freeze Bombs that get "blasted" are "flung" like Timed Bombs.  However!  Instead of "blasting" their neighbors, Freeze Bombs "freeze" their neighbors:

  * Frozen Timed Bombs and Frozen Freeze Bombs pause their countdown for 5 seconds.

  * Frozen Contact Bombs are desensitized to impacts for 5 seconds.

  * Freezing doesn't affect Remote Control bombs.

There are a lot of decorative objects that are immune to blasting and freezing: trees, rocks, and--strangely enough--beavers and bullrushes.  However, you can destroy bushes by blasting them.

If Ranger Jim gets blasted or frozen, the level is over and you have to restart.

Water and Floating Objects
--------------------------

Most water is still water.  However, some water is flowing in a particular direction.  You can tell what water is flowing water by paying attention to the ripples in the water: when the ripples are moving, that shows you what direction that patch water is flowing in.

Flowing water will push objects along, like floating logs, or bombs that are dropped into water.  Objects in flowing water move at the rate of one screen tile per second.

Objects in flowing water that get pushed up against something get stuck.  Once the obstacle is removed the object will resume floating along.

Ranger Jim can step on most floating objects.  There are only a few he can't, like beavers and bullrushes.  If Ranger Jim steps on a floating object that's in flowing water, he can ride on top!

Ranger Jim can't pick up any object that's floating in water.

If Ranger Jim falls in the water, the level is over and you have to restart.


Flinging
--------

Objects can occasionally move very quickly.  This is called being "flung".

Objects can get flung two different ways:

* Timed Bombs that get "detonated" are flung one square away from the explosion.

* When Ranger Jim drops a bomb on top of a floating object, the bomb is "flung" over the object, heading away from Ranger Jim.  If there is a series of floating objects all in a row, the bomb will "skip" along all of them until it lands in open water... or on a distant shore!


Making Your Own Levels
----------------------

You can make your own Dynamite Valley levels!

First, open up the "src/levels" directory.  Dynamite Valley levels are individual text files in this directory.  The easiest way to make a new level is to copy an existing level, then edit it however you like.  Edit the level in your favorite text editor, then save your new text file in "src/levels" with the ".txt" file extension.  You can play your own levels with "run_game.py <name of level>".  For example, if you name your level "fred.txt", you can play it with "run_game.py fred".

Here's a quick description of the level format.  Levels are text files, using simple ASCII files.  Each level text file has three sections: the "tile map", followed by the "legend", and finally the "metadata".

The first section is the "tile map" for the level.  This must be exactly be 12 characters across and 13 characters tall.  The "tile map" is a sort of ASCII art drawing of the level, where one character maps to one tile on the screen.

After the "tile map" there should be one or more blank lines, and after those blank lines shoulld be the "legend".

The "legend" establishes what the characters of the tile map represent.  A "legend" line is a single character, followed by a space, followed by a definition of what that character represents in the "tile map".  There's also a default "legend.txt" shared by all levels containing all the most commonly-used tiles.

(What are the possible legal "definitions" for a legend line?  It's hard to describe.  Just find a tile in the game that does what you want, and look in the level where it was used to se what the relevant "legend line" was.)

After the "legend" there should be one or more blank lines, followed by the "metadata".

The "metadata" establishes various other facts about the level.  The format of a "metadata" line is: a noun with a colon at either end, followed by one or more spaces, followed by the value for that metadata.

Here are all the valid nouns for metadata lines:

* :title: The name of the level, displayed at the loading screen.
* :hint: The "hint" for the level, displayed at the loading screen.
* :author: The "author" for the level, displayed at the loading screen.
* :next: The name of the next level.  When the player finishes this level, the game will automatically switch to this level.

The only required metadata is "next".  All the others are optional and have sensible default values.


Stuff We Didn't Get To
----------------------

Some ideas we didn't have time to explore during PyWeek 26:

* Giant Bombs, which blast all squares within a "Manhattan distance" of 2.

* Moving beavers, which would swim back and forth in a predictable pattern.  Swimming beavers would push any floating object (including a Contact Bomb, which it would not set off).  Blasting a beaver would be an automatic level failure--you can't hurt the wildlife, you're a park ranger!
