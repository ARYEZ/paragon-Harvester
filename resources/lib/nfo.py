# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The NFO files Kodi reads, and the one repair job they sometimes need.

Building the text and writing it out are separate on purpose. The text is
what has to be right -- valid XML, nothing in it Kodi's database will refuse
-- and a test can read a string. Writing a string to a file is not where the
mistakes are.
"""

import io
import os

from xml.sax.saxutils import escape as xml_escape

import text as text_lib

# What goes in the stream details when ffprobe is not installed or cannot read
# the file. Kodi works the real numbers out for itself when it scans, so these
# are a shape for the file to have rather than a claim about the video.
DEFAULT_STREAM = {
    'video': {'codec': 'h264', 'width': 1920, 'height': 1080,
              'aspect': 1.778, 'duration_seconds': 0,
              'scantype': 'progressive'},
    'audio': {'codec': 'aac', 'channels': 2},
}

EPISODE_TEMPLATE = u"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<episodedetails>
    <title>%(title)s</title>
    <showtitle>%(showtitle)s</showtitle>
    <userrating>0</userrating>
    <top250>0</top250>
    <season>%(season)s</season>
    <episode>%(episode)s</episode>
    <plot>%(plot)s</plot>
    <mpaa>TV-14</mpaa>
    <playcount>0</playcount>
    <lastplayed>%(now)s</lastplayed>
    <aired>%(aired)s</aired>
    <genre>%(genre)s</genre>
    <dateadded>%(date_added)s</dateadded>
    <file>%(filename)s</file>
    <fileinfo>
        <streamdetails>
            <video>
                <durationinseconds>%(duration)s</durationinseconds>
                <codec>%(vcodec)s</codec>
                <aspect>%(aspect)s</aspect>
                <width>%(width)s</width>
                <height>%(height)s</height>
                <scantype>%(scantype)s</scantype>
            </video>
            <audio>
                <codec>%(acodec)s</codec>
                <channels>%(channels)s</channels>
            </audio>
        </streamdetails>
    </fileinfo>
    <generator>
        <appname>Paragon Harvester</appname>
        <appversion>%(version)s</appversion>
        <kodiversion>17</kodiversion>
        <datetime>%(stamp)s</datetime>
    </generator>
</episodedetails>"""

SHOW_TEMPLATE = u"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<tvshow>
    <title>%(title)s</title>
    <showtitle></showtitle>
    <sorttitle clear="true">%(title)s</sorttitle>
    <originaltitle>%(title)s</originaltitle>
    <!-- No valid ID was defined - using internal DB ID as fallback -->
    <uniqueid default="true" type="mediaelch_fallback">1</uniqueid>
    <userrating>0</userrating>
    <top250>0</top250>
    <episode>1</episode>
    <season>1</season>
    <plot>%(plot)s</plot>
    <mpaa>TV-14</mpaa>
    <premiered></premiered>
    <year></year>
    <dateadded></dateadded>
    <status>Continuing</status>
    <runtime>5</runtime>
    <trailer></trailer>
    <genre>%(genre)s</genre>
    <generator>
        <appname>MediaElch</appname>
        <appversion>2.12.0</appversion>
        <kodiversion>17</kodiversion>
        <datetime>%(stamp)s</datetime>
    </generator>
</tvshow>"""


def _safe(value):
    """A value as XML text: storable by Kodi, and escaped."""
    return xml_escape(text_lib.strip_wide(value) if value else u'')


def episode_nfo(show_name, episode_title, season, episode, file_path, genre,
                date_added, series_summary, description=None, aired=None,
                stream=None, now=None, stamp=None, version=u'1.0.0'):
    """The text of one episode's NFO.

    `description` is the cleaned YouTube description when there is one, and
    `aired` the upload date; both are worked out by the caller, because
    fetching them is the part that needs the network and this part must not.
    """
    stream = stream or DEFAULT_STREAM
    plot = text_lib.generate_plot(show_name, episode_title, series_summary,
                                 description)
    return EPISODE_TEMPLATE % {
        'title': _safe(text_lib.clean_title(episode_title)),
        'showtitle': _safe(text_lib.clean_title(show_name)),
        'season': season,
        'episode': episode,
        'plot': _safe(plot),
        'now': now or date_added,
        'aired': aired or date_added,
        'genre': _safe(genre),
        'date_added': date_added,
        'filename': _safe(os.path.basename(file_path)),
        'duration': stream['video']['duration_seconds'],
        'vcodec': _safe(stream['video']['codec']),
        'aspect': stream['video']['aspect'],
        'width': stream['video']['width'],
        'height': stream['video']['height'],
        'scantype': _safe(stream['video']['scantype']),
        'acodec': _safe(stream['audio']['codec']),
        'channels': stream['audio']['channels'],
        'version': version,
        'stamp': stamp or date_added,
    }


def tvshow_nfo(show_name, genre, summary, stamp):
    """The text of a show's tvshow.nfo."""
    return SHOW_TEMPLATE % {
        'title': _safe(text_lib.clean_title(show_name)),
        'plot': _safe(summary),
        'genre': _safe(genre),
        'stamp': stamp,
    }


def write(path, content):
    """Write an NFO. True if it went down.

    Always UTF-8 and always through io.open, because Python 2's plain open()
    writes bytes and would refuse the first accented character in a title.
    """
    try:
        handle = io.open(path, 'w', encoding='utf-8')
        try:
            handle.write(content)
        finally:
            handle.close()
        return True
    except (IOError, OSError):
        return False


def sanitise(root_folder):
    """Strip what Kodi cannot store from every NFO under `root_folder`.

    Returns the paths that changed. This is the repair job for a library that
    already has emoji in it: Kodi's scan fails with MySQL error 1366 and the
    episode never appears, and there is no way to tell that from the library
    other than noticing something missing.
    """
    changed = []
    for here, _dirs, found in os.walk(root_folder):
        for name in sorted(found):
            if not name.lower().endswith('.nfo'):
                continue
            path = os.path.join(here, name)
            try:
                handle = io.open(path, 'r', encoding='utf-8')
                try:
                    before = handle.read()
                finally:
                    handle.close()
            except (IOError, OSError, ValueError):
                continue
            after = text_lib.strip_wide(before)
            if after != before and write(path, after):
                changed.append(path)
    return changed
