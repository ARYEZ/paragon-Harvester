# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

Everything the harvester does to a piece of text.

All of it is pure: a string in, a string out, no Kodi and no filesystem. That
is deliberate, because this is where the add-on is most likely to be wrong in
a way nobody notices -- a title cleaned too hard, a plot that swallowed the
description, a character that stops Kodi's database accepting the NFO -- and
pure functions are the part a test can hold still and look at.

Ported from video_organizer_enhanced.py, which is still in this repository and
still runs on its own. The rules below are that script's rules; where the port
had to change something, the comment says why.
"""

import re

# Filename characters Windows refuses. The destination is a Windows drive, so
# this is not optional there, and stripping them on any other platform costs
# nothing.
INVALID_FILENAME_CHARS = ('<', '>', ':', '"', '/', '\\', '|', '?', '*')

# Suffixes YouTube titles carry that say nothing about the episode. Order
# matters: the longer ones are tried first so " official lyric video" is not
# left with " official" after " lyric video" has gone.
TITLE_SUFFIXES = (
    ' official lyric video', ' official music video', ' official visualizer',
    ' official video', ' official audio', ' music video', ' lyric video',
    ' visualizer', ' hd', ' hq', ' 4k', ' 8k',
)

# The same, written with a hyphen, which is how half of YouTube spells it.
TITLE_HYPHEN_SUFFIXES = (
    ' - official video', ' - music video', ' - lyric video', ' - audio',
    ' - hd', ' - 4k',
)

# Tried longest first, which the script did not do: it ran the plain suffixes
# before the hyphenated ones, so "Midnight Drive - Official Video" lost
# " official video" and kept the hyphen, and the filename came out as
# "01x01 - Midnight Drive - - Show". Sorting by length makes the longest match
# win wherever two rules overlap.
SUFFIXES_LONGEST_FIRST = tuple(sorted(
    TITLE_SUFFIXES + TITLE_HYPHEN_SUFFIXES, key=len, reverse=True))

# Where a title stops being the title and starts being credits.
TITLE_SPLITS = (' ft. ', ' feat. ', ' featuring ', ' by ')

# Lines in a YouTube description that are advertising rather than description.
PROMOTIONAL = (
    'merch store', 'merch:', 'store:',
    'patreon', 'support me on',
    'special thanks', 'thanks to',
    'follow me', 'social media', 'twitter', 'instagram', 'facebook',
    'music:', 'music by', 'song:', 'songs used',
    'licensed under', 'creative commons', 'cc by',
    'subscribe', 'like and subscribe',
    'check out', 'links:',
    'equipment:', 'gear:',
    'discord:', 'join my discord',
    'outro music', 'background music',
    'footage from', 'clips from',
    u'▬▬▬', u'━━━', u'═══', u'───',
    'download', 'stream',
    'listen to', 'available now', 'out now',
    'spotify', 'apple music', 'itunes',
    'descargar', 'apoyo',
    'lyrics', 'letra',
    '[verse', '[chorus', '[bridge', '[intro', '[outro',
    '(verse', '(chorus', '(bridge', '(intro', '(outro',
    'official lyric video', 'lyric video',
)

LYRIC_MARKERS = ('[verse', '[chorus', '[bridge', '[intro', '[outro',
                 '[pre-', '[post-')
LYRIC_STARTS = ('verse ', 'chorus ', 'bridge ', 'intro:', 'outro:',
                'pre-chorus', 'post-chorus')
SHORTENERS = ('.lnk.to/', 'bit.ly/', 'youtu.be/', 'smarturl.')
DECORATION = re.compile(u'[▬━═─_\\-=*#»«]')

PLOT_LIMIT = 500

MUSIC_WORDS = ("band", "music", "artist", "singer", "rock", "metal", "pop",
               "jazz", "hip hop", "rap", "orchestra")
COMEDY_WORDS = ("comedy", "funny", "laugh", "humor", "stand up", "standup")
DOCUMENTARY_WORDS = ("documentary", "nature", "history", "science", "discover",
                     "explore")


def strip_wide(text):
    """Drop every character Kodi's database cannot store.

    Kodi's MySQL tables are plain `utf8`, which is three bytes at most, so a
    character above U+FFFF makes a library scan fail with error 1366 and the
    episode simply never appears. Emoji in a plot is the usual culprit.

    The surrogate half of this is the porting bug that took the longest to
    see. Python 3 holds an emoji as one character above U+FFFF, so the script
    only had to test for that. Python 2 on Windows is a narrow build: the same
    emoji is *two* characters, each inside the surrogate range and each below
    U+FFFF, so that test passes them both through and what reaches the NFO is
    a broken pair -- worse than the emoji was. Both are dropped here.
    """
    if not text:
        return text
    return u''.join(ch for ch in text
                    if ord(ch) <= 0xFFFF and not 0xD800 <= ord(ch) <= 0xDFFF)


def clean_title(title):
    """A title as it is written into an NFO: trimmed, title case, storable."""
    if not title:
        return title
    return strip_wide(title.strip().title())


def sanitise_filename(text):
    """`text` with the characters a filename may not contain taken out."""
    if not text:
        return u''
    for char in INVALID_FILENAME_CHARS:
        text = text.replace(char, u'')
    return text.strip()


def clean_episode_title(title):
    """An episode title with YouTube's decoration taken off.

    Every rule here can go too far -- "Live (1975)" is a title, not a title
    with a bracket on it -- so the whole thing backs out if what is left is
    under three characters, and the original is used instead. That guard is
    the script's and it is the reason this can be as aggressive as it is.
    """
    if not title:
        return title
    original = title

    # Anything in brackets: (Official Video), [HD], {Live}, <br>.
    for pattern in (r'\s*\([^)]*\)', r'\s*\[[^\]]*\]', r'\s*\{[^}]*\}',
                    r'\s*<[^>]*>'):
        title = re.sub(pattern, u'', title)

    for suffix in SUFFIXES_LONGEST_FIRST:
        title = re.sub(re.escape(suffix) + u'$', u'', title,
                       flags=re.IGNORECASE)

    for split in TITLE_SPLITS:
        if split in title.lower():
            # Split on the text as it is actually written, which may be
            # capitalised differently from the marker.
            at = title.lower().index(split)
            title = title[:at]

    title = u' '.join(title.split()).rstrip(u'-').strip()
    if not title or len(title) < 3:
        return strip_wide(original)
    return strip_wide(title)


def _is_decoration(line):
    """True for a line that is mostly rule characters rather than words."""
    stripped = line.strip()
    if not stripped:
        return False
    return len(DECORATION.findall(line)) / float(len(stripped)) > 0.5


def clean_description(description, video_title, channel_name):
    """A YouTube description reduced to the part that describes the video.

    Reads the description from the top and stops at the first promotional
    line, because on YouTube the advertising is always after the writing. A
    promotional line before any writing is skipped instead of stopping it, so
    a description that opens with "Subscribe!" is not thrown away whole.
    """
    fallback = u'%s from %s' % (video_title, channel_name)
    if not description:
        return fallback

    kept = []
    for line in description.split(u'\n'):
        lowered = line.lower().strip()
        if not line.strip():
            continue
        if 'http://' in lowered or 'https://' in lowered or 'www.' in lowered:
            continue
        if any(domain in lowered for domain in SHORTENERS):
            continue
        if u'»' in line or u'«' in line:
            continue
        if any(marker in lowered for marker in LYRIC_MARKERS):
            continue
        if lowered.startswith(LYRIC_STARTS):
            continue
        if _is_decoration(line):
            continue

        if any(word in lowered for word in PROMOTIONAL):
            if kept:
                break
            continue
        kept.append(line.strip())

    cleaned = re.sub(r'\s+', u' ', u' '.join(kept)).strip()
    if len(cleaned) < 10:
        return fallback
    if len(cleaned) > PLOT_LIMIT:
        cleaned = cleaned[:PLOT_LIMIT - 3] + u'...'
    return strip_wide(cleaned)


def suggest_show_summary(show_name):
    """A first summary for a show nobody has described yet.

    Guessed from the name, and meant to be edited rather than kept. It exists
    so that a show always has a plot in its tvshow.nfo, since Kodi shows an
    empty one as a blank page.
    """
    lowered = show_name.lower()
    if any(word in lowered for word in MUSIC_WORDS):
        return (u'A collection of powerful tracks by the acclaimed musical act '
                u'%s. Experience their unique sound and artistic evolution '
                u'through this carefully curated selection.' % show_name)
    if any(word in lowered for word in COMEDY_WORDS):
        return (u'Hilarious performances from %s that showcase their unique '
                u'comedic style and timing. Each episode delivers memorable '
                u'jokes and situations that will leave you laughing.'
                % show_name)
    if any(word in lowered for word in DOCUMENTARY_WORDS):
        return (u'An insightful documentary series featuring %s. Each episode '
                u'explores fascinating subjects with depth and clarity, '
                u'providing viewers with a new perspective.' % show_name)
    return (u'A captivating collection featuring %s. This series showcases '
            u'their best work, highlighting the unique style and creativity '
            u'that has earned them recognition.' % show_name)


def generate_plot(show_name, episode_title, series_summary=None,
                  youtube_description=None):
    """What goes in an episode's plot, best source first."""
    if youtube_description and len(youtube_description) > 10:
        return youtube_description
    if series_summary:
        return u'%s This one is called %s.' % (series_summary, episode_title)
    return u"Episode '%s' of %s." % (episode_title, show_name)
