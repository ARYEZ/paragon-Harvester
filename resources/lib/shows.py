# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

What the harvester remembers about each show: where its numbering is up to,
what it is called, what it is about, and which YouTube channel it comes from.

One JSON file, the way the script kept summaries.json, so it can still be
read and hand-edited. It lives in the add-on's profile folder rather than
beside the code, because an add-on's own folder is replaced wholesale by
every update and the list would go with it.
"""

import io
import json
import os

STORE_FILE = 'shows.json'

# What a show looks like before anybody has told us anything about it.
BLANK = {'season': 1, 'episode': 1, 'genre': None, 'summary': None,
         'channel': None}

# Where a season ends. The script hardcoded 24; it is a setting now, and this
# is what it falls back to.
DEFAULT_EPISODES_PER_SEASON = 24


def store_path(profile):
    return os.path.join(profile, STORE_FILE)


def key_for(show_name):
    """The name a show is filed under.

    Title case, so that "lofi girl", "Lofi Girl" and "LOFI GIRL" are one show
    and not three folders. It is also the folder name on disk, which is why
    the numbering and the filing cannot disagree about it.
    """
    return (show_name or u'').strip().title()


def normalise(entry, episodes_per_season=DEFAULT_EPISODES_PER_SEASON):
    """One show as it comes off disk, whatever shape it was written in.

    The oldest files hold a list rather than an object, from a version that
    stored (season, episode, genre). That form is still read, because the
    alternative is a user's numbering silently starting again at 01x01.
    """
    if isinstance(entry, (list, tuple)):
        season = entry[0] if len(entry) > 0 else 1
        episode = entry[1] if len(entry) > 1 else 1
        genre = entry[2] if len(entry) > 2 else None
        entry = {'season': season, 'episode': episode, 'genre': genre}
    if not isinstance(entry, dict):
        return dict(BLANK)

    clean = dict(BLANK)
    for field in ('genre', 'summary', 'channel'):
        value = entry.get(field)
        clean[field] = value if value else None
    try:
        clean['season'] = max(1, int(entry.get('season', 1)))
    except (TypeError, ValueError):
        clean['season'] = 1
    try:
        # Zero is a real value: it means "reset, and the next file is the
        # first", because the number a file gets is the number after the one
        # stored. Clamping it to 1 the way the season is clamped would make a
        # show that was started over begin again at 01x02.
        clean['episode'] = max(0, int(entry.get('episode', 1)))
    except (TypeError, ValueError):
        clean['episode'] = 1
    return clean


def load(profile, episodes_per_season=DEFAULT_EPISODES_PER_SEASON):
    """Every show that is known, keyed by name. Empty when there is no file."""
    path = store_path(profile)
    if not os.path.isfile(path):
        return {}
    try:
        handle = io.open(path, 'r', encoding='utf-8')
        try:
            raw = json.load(handle)
        finally:
            handle.close()
    except (IOError, OSError, ValueError):
        # A store that cannot be read is not a store that should be
        # overwritten in silence: the caller is told by the empty answer, and
        # save() will only write once something has been harvested.
        return {}
    if not isinstance(raw, dict):
        return {}
    return dict((key_for(name), normalise(entry, episodes_per_season))
                for name, entry in raw.items())


def save(profile, data):
    """Write the list back. True if it went down."""
    try:
        handle = io.open(store_path(profile), 'w', encoding='utf-8')
        try:
            # ensure_ascii keeps the file readable on Python 2, where json
            # hands back bytes for a non-ASCII name otherwise.
            handle.write(json.dumps(data, indent=4, sort_keys=True,
                                    ensure_ascii=False))
        finally:
            handle.close()
        return True
    except (IOError, OSError, TypeError, ValueError):
        return False


def register(data, show_key, summary=None, genre=None, channel=None):
    """Add a show that has not been seen before, at 01x01."""
    entry = dict(BLANK)
    entry['summary'] = summary or None
    entry['genre'] = genre or None
    entry['channel'] = channel or None
    data[show_key] = entry
    return entry


def advance(data, show_key, episodes_per_season=DEFAULT_EPISODES_PER_SEASON):
    """Move a known show on by one episode, rolling into the next season.

    Rolling at the limit rather than counting on forever is what keeps a
    channel with four hundred uploads from becoming one season of four
    hundred episodes, which Kodi will show but nobody can navigate.
    """
    entry = data.get(show_key)
    if entry is None:
        return register(data, show_key)
    entry = normalise(entry, episodes_per_season)
    entry['episode'] += 1
    if entry['episode'] > max(1, episodes_per_season):
        entry['episode'] = 1
        entry['season'] += 1
    data[show_key] = entry
    return entry


def reset(data, show_key, summary=None, genre=None, channel=None):
    """Start a show over at 01x01, keeping its channel unless told otherwise.

    The channel is kept by default because it is the one field that took
    looking up, and the reason to reset is almost always the numbering.
    """
    existing = data.get(show_key) or {}
    if channel is None:
        channel = existing.get('channel')
    entry = register(data, show_key, summary, genre, channel)
    # Not one. A show that is already known has its number advanced before the
    # file is written, so leaving this at one would file the next video as
    # 01x02 under a menu row that says it starts again at 01x01.
    entry['episode'] = 0
    return entry
