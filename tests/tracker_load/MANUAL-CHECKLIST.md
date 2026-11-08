# Manual check of the tracker files, each release

For the owner, on Windows, with the original ZTracker and ZoraTracker (the WPF build). What the machine tests cannot see: how it looks, the dialogs, and ZTracker's dungeon import.

Make the files: `python3 -m tests.tracker_load.samples SOMEFOLDER`. Each name is `FAMILY-Ln-seedN`: `z1r` is Z1R flags only, `zora` has ZORA flags; L1 Basic, L2 Medium, L3 Full. Each has `.tracker.json` (load it) and `.spoiler.txt` (compare with it).

For each file, in ZoraTracker, and for the `z1r-*` files also in ZTracker:

1. Load Save, pick the file. ZTracker shows the version box ("will probably fail", click Attempt Load): expected. ZoraTracker shows no box.
2. Tabs 1 to 9 each show a map; the number of rooms matches the log's level map.
3. Each level's entrance arrow is on the side the log gives.
4. Stairway pairs: every `Transport` number appears in exactly two rooms of a level, and they are the log's pairs.
5. Item boxes: each level's boxes and the six overworld item places match "Item places" in the log.
6. Overworld: each cave, shop and level entrance is marked where the log says.

Medium and Full also:

7. Floor-drop marks (Heart, Triforce, other key item) are in the rooms the log names; item cellars show as basement rooms.

Full also:

8. Ganon's room shows the "G" icon and Zelda's room the red "Z".
9. Yellow edges are locked doors and purple edges are shutters.
10. The monsters shown are those in the log's room lines.
11. Minor floor drops (key, bombs, five rupees, map, compass) match the log.

ZTracker only:

12. The Wood Sword, Magical Sword and Letter boxes stay empty (ids above 14: expected, not a new bug).
13. Dungeon maps load without an error box. If a "Loading the save file failed" box appears, note the text and the file name.

Record the file name, the tracker and the step for anything that differs.
