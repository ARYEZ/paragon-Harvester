# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

Reading a filename, and writing the one that replaces it.

Pure, like text.py, and separate from it because these rules are about files
rather than about English: which eleven characters are a YouTube id, which
half of a filename is the show, and what the long name Kodi's library reads
best is made of.
"""

import os
import re

import text as text_lib

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv')

# A YouTube id is exactly eleven of these, which is specific enough to find
# one inside a downloaded filename without matching anything else.
VIDEO_ID = re.compile(r'\[([a-zA-Z0-9_-]{11})\]')

# "Show - Episode.ext", then the same thing with any separator, which is what
# a downloader writes when it is not asked to do otherwise.
FILENAME_PATTERNS = (
    re.compile(r'(.+?)\s*[-_]\s*(.+?)\.(\w+)$'),
    re.compile(r'(.+?)[\s_\.-]+(.+?)\.(\w+)$'),
)

# Width to the number people call it. Read off the video rather than the
# filename, so a file called 1080p that is not gets named for what it is.
RESOLUTIONS = ((3800, '2160'), (1900, '1080'), (1260, '720'))


def is_video(name):
    return name.lower().endswith(VIDEO_EXTENSIONS)


def video_id(filename):
    """The YouTube id inside a filename, or None.

    Worth a lot: with an id the metadata is one exact lookup, and without it
    the add-on has to search for the video by name and hope.
    """
    found = VIDEO_ID.search(filename or '')
    return found.group(1) if found else None


def split_filename(filename):
    """(show, episode) read out of a filename, or (None, None).

    Only used for a file sitting loose in the source folder. A file in a
    subfolder takes the folder's name as the show, which is both more
    reliable and how anyone downloading a series lays it out.
    """
    for pattern in FILENAME_PATTERNS:
        found = pattern.match(filename or '')
        if found:
            show, episode, _extension = found.groups()
            return show, episode
    return None, None


def resolution_for(width):
    """The label for a video that wide."""
    try:
        width = int(width)
    except (TypeError, ValueError):
        return '480'
    for edge, label in RESOLUTIONS:
        if width >= edge:
            return label
    return '480'


def episode_filename(season, episode, episode_title, extension):
    """The short name a file takes when it is filed: S01E02 - Title.mp4."""
    return u'S%02dE%02d - %s%s' % (season, episode,
                                   text_lib.sanitise_filename(episode_title),
                                   extension)


def extended_name(season, episode, episode_title, show_name, genre,
                  resolution, channels, audio_codec):
    """The long name, which is what the library ends up holding.

    Everything about the episode in the filename itself, so that a library
    rebuilt from nothing but the files still knows what each one is.
    """
    parts = (
        u'%02dx%02d' % (int(season), int(episode)),
        text_lib.sanitise_filename(episode_title),
        text_lib.sanitise_filename(show_name),
        text_lib.sanitise_filename(genre or u'Unknown') or u'Unknown',
        u'%s' % resolution,
        u'%s' % channels,
        (u'%s' % audio_codec).upper(),
        u'None',
    )
    return u' - '.join(parts)


def free_path(folder, name):
    """`name` in `folder`, with a number added if that is taken.

    The counter goes on the stem rather than the whole name, so a second
    copy of a video is thing_1.mp4 and not thing.mp4_1.
    """
    stem, extension = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, u'%s_%d%s' % (stem, counter,
                                                      extension))
        counter += 1
    return candidate
