# Paragon Harvester

Takes the videos piling up in a download folder, works out which show each one
belongs to, files it under that show with a season and episode number, and
writes the NFO Kodi reads. Part of the Paragon TV Project.

It began as `video_organizer_enhanced.py`, a console script run by hand on one
Windows machine. That script is still here and still runs. This is the same
work done from inside Kodi 17.6, on a schedule or on demand.

## What it does to a file

1. Works out the show. A video in a subfolder takes the folder's name; one
   sitting loose in the source folder is read apart at the dash.
2. Asks YouTube what it is. The eleven-character id in a downloaded filename
   is an exact lookup; without one it searches, scoped to the show's channel
   when one is set, because "Sunset" matches half of YouTube otherwise.
3. Moves it under the show, numbered: `S01E02 - Sunset Drive.mp4`.
4. Writes the episode NFO, with the cleaned description as the plot and the
   upload date as the aired date.
5. Renames the pair to the long form the library reads:
   `01x02 - Sunset Drive - Lofi Girl - Music - 1080 - 2 - AAC - None.mp4`.

A show it has never seen is the only thing it asks about: what it is, its
genre, and its channel. Everything after that goes through in silence.

## Running it

**From the menu.** Open the add-on: run a pass now, see what it knows, start a
show over, or clean up NFOs.

**On a schedule.** Turn on *Watch the download folder* in settings and it
looks every few minutes. It never asks when it runs itself: a new show is set
up from the defaults and you are told which ones those were.

**From a keymap or a shortcut.**

```
RunScript(script.paragon.harvester)                  the menu
RunScript(script.paragon.harvester,action=run)       a pass, asking if it must
RunScript(script.paragon.harvester,action=quiet)     a pass, asking nothing
RunScript(script.paragon.harvester,action=sanitise)  clean up the NFOs
```

## What it needs

**yt-dlp**, for anything YouTube knows. It is a Python 3 program, so a Kodi
17.6 add-on cannot import it; this runs it as a program instead, which means
the add-on belongs on the box that has it. Without yt-dlp everything still
files and every episode keeps its generated plot.

**ffprobe**, optionally, for the resolution and audio in the long filename.
Without it the NFO takes a default shape and Kodi works the real numbers out
when it scans.

Both can be named in full in settings if they are not on the path.

## A file still being written

A download in progress is a file that grows. The service leaves a file alone
until it has not changed for *Leave a new file alone for* seconds, because
filing one halfway through moves a truncated video into the library and leaves
the downloader writing to a path that is no longer there.

## Clean up NFOs

Kodi's MySQL tables are plain `utf8`, three bytes at most, so an emoji in a
plot fails the library scan with error 1366 and the episode simply never
appears. **Clean up NFOs** reads every NFO under the destination, takes out
what cannot be stored, and asks Kodi to re-read the folders that changed.

Everything written from here is cleaned on the way out, so this is for a
library that already has emoji in it.

## Where its memory lives

One JSON file, `shows.json`, in the add-on's profile folder. It holds each
show's numbering, summary, genre and channel, and it can be read and edited by
hand. It is not in the add-on's own folder, which every update replaces.

## Tests

```
python3 tests/test_harvester.py     what it does
python3 tests/check_py2.py          what Kodi 17.6's Python 2.7 can parse
python3 tests/validate_addon.py     what Kodi reads before any of it runs
```

The add-on runs on Python 2.7 and the tests run on Python 3, which is the
arrangement every Paragon add-on uses: behaviour is the same in both, and
`check_py2.py` reads the AST of every shipped file for what 2.7 cannot parse.
