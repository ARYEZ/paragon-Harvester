# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The work itself: a folder of downloaded videos in, a library of shows out.

One file's journey is the whole add-on. Work out which show it belongs to,
ask YouTube what it is, move it under that show, number it, write the NFO,
and rename it to the long form the library reads. Everything else here is
either finding the files or writing down what happened.

Nothing in this module talks to Kodi or to a person. What it needs from the
outside arrives as objects: a `probe` for the two outside programs, and an
`asker` for the one question it ever has to ask. That is what makes a harvest
something a test can run start to finish on a temporary folder, which matters
more here than anywhere else in the add-on -- this is the code that moves
somebody's files.
"""

import os
import shutil
from datetime import datetime

import names
import nfo
import shows as shows_lib
import text as text_lib

# What the script wrote into every episode, and this keeps writing. A fixed
# date rather than today's: it is the date Kodi sorts "recently added" by, and
# filing a hundred old videos should not push everything else off that list.
DATE_ADDED = u'2000-01-01'


class Asker(object):
    """What the engine asks a person, and the answer when nobody is there.

    A new show is the only thing worth asking about: what it is, what genre
    it is, and which YouTube channel it comes from. Everything after that is
    the same answer every time, which is what a service is for.
    """

    def about_new_show(self, show_key, suggested_summary, default_genre,
                       default_channel):
        """(summary, genre, channel) for a show never seen before.

        The base class takes the suggestion and the defaults, which is the
        add-on running unattended.
        """
        return suggested_summary, default_genre, default_channel


class Report(object):
    """What a pass did, in the terms somebody would ask about it."""

    def __init__(self):
        self.seen = 0
        self.filed = []
        self.skipped = []
        self.failed = []
        self.new_shows = []

    @property
    def count(self):
        return len(self.filed)

    def describe(self):
        if not self.seen:
            return u'Nothing to file'
        parts = [u'%d of %d filed' % (self.count, self.seen)]
        if self.new_shows:
            parts.append(u'%d new show(s)' % len(self.new_shows))
        if self.skipped:
            parts.append(u'%d skipped' % len(self.skipped))
        if self.failed:
            parts.append(u'%d failed' % len(self.failed))
        return u', '.join(parts)


class Harvester(object):
    """A source folder, a destination, and everything needed to get between.

    `settle_seconds` is the one thing here that has no equivalent in the
    script. A script is run when the downloads have finished; a service looks
    every few minutes and will happily pick up a file still being written, so
    a file has to have stopped changing before it is touched.
    """

    def __init__(self, source, destination, profile, probe, asker=None,
                 default_genre=None, default_channel=None,
                 episodes_per_season=shows_lib.DEFAULT_EPISODES_PER_SEASON,
                 settle_seconds=0, overwrite_nfo=False, log=None, now=None):
        self.source = source
        self.destination = destination
        self.profile = profile
        self.probe = probe
        self.asker = asker or Asker()
        self.default_genre = default_genre or None
        self.default_channel = default_channel or None
        self.episodes_per_season = episodes_per_season
        self.settle_seconds = settle_seconds
        self.overwrite_nfo = overwrite_nfo
        self.log = log or (lambda message: None)
        self.now = now or datetime.now

    # -- finding the work --------------------------------------------------

    def videos(self):
        """Every video under the source folder, deepest name first."""
        found = []
        for here, _dirs, files in os.walk(self.source):
            for name in sorted(files):
                if names.is_video(name):
                    found.append(os.path.join(here, name))
        return found

    def has_settled(self, path, seconds=None):
        """True when a file has not been written to for long enough.

        A download in progress is a file that grows; filing one halfway
        through moves a truncated video into the library and leaves the
        downloader writing to a path that is no longer there.
        """
        seconds = self.settle_seconds if seconds is None else seconds
        if seconds <= 0:
            return True
        try:
            age = os.path.getmtime(path)
        except OSError:
            return False
        return (self.epoch_now() - age) >= seconds

    def epoch_now(self):
        """Seconds since the epoch, as a number a test can stand still."""
        import time
        return time.time()

    # -- what a file says about itself -------------------------------------

    def show_and_episode(self, path):
        """(show, episode title) for a file, or (None, None) if unreadable.

        A file in a subfolder takes the folder's name as its show and its own
        name as the episode. That is both the more reliable rule and the way
        anyone downloading a series already lays it out; only a file sitting
        loose in the source folder has to be read apart.
        """
        filename = os.path.basename(path)
        folder = os.path.dirname(path)
        stem, _extension = os.path.splitext(filename)

        relative = os.path.relpath(folder, self.source)
        if relative not in ('.', '', self.source):
            return os.path.basename(folder), stem
        return names.split_filename(filename)

    def metadata_for(self, filename, show_name, episode_title, channel):
        """What YouTube knows about this file, or None.

        The id in the filename is the good case: one exact lookup, no guess.
        Without one there is a search, and the channel is what keeps that
        search honest.
        """
        found = names.video_id(filename)
        if found:
            self.log(u'video id in the filename: %s' % found)
            return self.probe.metadata(found)

        query = u'%s %s' % (show_name, episode_title)
        self.log(u'searching for: %s' % query)
        found = self.probe.search(query, channel)
        if not found:
            self.log(u'no match on YouTube; keeping the generated plot')
            return None
        return self.probe.metadata(found)

    # -- one file ----------------------------------------------------------

    def process(self, path, data, report):
        """File one video. True if it was filed."""
        filename = os.path.basename(path)
        show_name, episode_title = self.show_and_episode(path)
        if not show_name or not episode_title:
            self.log(u'not a name this can read: %s' % filename)
            report.skipped.append(path)
            return False

        show_key = shows_lib.key_for(show_name)
        fresh = show_key not in data
        if fresh:
            summary, genre, channel = self.asker.about_new_show(
                show_key, text_lib.suggest_show_summary(show_name),
                self.default_genre, self.default_channel)
            shows_lib.register(data, show_key, summary, genre, channel)
            report.new_shows.append(show_key)
        else:
            shows_lib.advance(data, show_key, self.episodes_per_season)
        entry = data[show_key]

        channel = entry.get('channel') or self.default_channel
        metadata = self.metadata_for(filename, show_name, episode_title,
                                     channel)
        episode_title = text_lib.clean_episode_title(episode_title)

        show_folder = os.path.join(self.destination, show_key)
        if not os.path.isdir(show_folder):
            try:
                os.makedirs(show_folder)
            except OSError as exc:
                self.log(u'cannot make %s: %s' % (show_folder, exc))
                report.failed.append(path)
                return False
            self.write_show_nfo(show_folder, show_name, entry)

        landed = self.move_in(path, show_folder, entry, episode_title, report)
        if landed is None:
            return False

        self.write_episode(landed, show_name, episode_title, entry, metadata)
        report.filed.append(landed)
        return True

    def move_in(self, path, show_folder, entry, episode_title, report):
        """Move the file under its show and give it its episode name.

        One move rather than the script's move-then-rename. The script put the
        file in under its download name and renamed it afterwards, which left
        a window where the library could be scanned and pick up a file about
        to be renamed underneath it.
        """
        _stem, extension = os.path.splitext(os.path.basename(path))
        wanted = names.episode_filename(entry['season'], entry['episode'],
                                        episode_title, extension)
        target = names.free_path(show_folder, wanted)
        try:
            shutil.move(path, target)
        except (IOError, OSError) as exc:
            self.log(u'cannot move %s: %s' % (os.path.basename(path), exc))
            report.failed.append(path)
            return None
        self.log(u'%s -> %s' % (os.path.basename(path),
                               os.path.basename(target)))
        return target

    def write_show_nfo(self, show_folder, show_name, entry):
        path = os.path.join(show_folder, 'tvshow.nfo')
        if os.path.exists(path):
            return False
        stamp = self.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        return nfo.write(path, nfo.tvshow_nfo(show_name, entry.get('genre'),
                                              entry.get('summary'), stamp))

    def write_episode(self, path, show_name, episode_title, entry, metadata):
        """The episode NFO, and the long filename that goes with it."""
        nfo_path = os.path.splitext(path)[0] + '.nfo'
        if os.path.exists(nfo_path) and not self.overwrite_nfo:
            self.log(u'NFO already there: %s' % os.path.basename(nfo_path))
            return path

        description = None
        aired = None
        if metadata:
            raw = metadata.get('description')
            if raw:
                description = text_lib.clean_description(
                    raw, episode_title, metadata.get('uploader') or show_name)
            uploaded = metadata.get('upload_date')
            if uploaded:
                try:
                    aired = datetime.strptime(uploaded, '%Y%m%d').strftime(
                        '%Y-%m-%d')
                except (TypeError, ValueError):
                    aired = None

        stream = self.probe.stream_info(path) or nfo.DEFAULT_STREAM
        now = self.now()
        nfo.write(nfo_path, nfo.episode_nfo(
            show_name, episode_title, entry['season'], entry['episode'],
            path, entry.get('genre'), DATE_ADDED, entry.get('summary'),
            description=description, aired=aired, stream=stream,
            now=now.strftime('%Y-%m-%d %H:%M:%S'),
            stamp=now.strftime('%Y-%m-%dT%H:%M:%SZ')))

        return self.rename_extended(path, nfo_path, show_name, episode_title,
                                    entry, stream)

    def rename_extended(self, path, nfo_path, show_name, episode_title, entry,
                        stream):
        """Rename the pair to the long form, and give back the video's path.

        The script read the stream details back out of the NFO it had just
        written to build this name. The numbers are already here, so this uses
        them: same name, one less way for the two to disagree.
        """
        wanted = names.extended_name(
            entry['season'], entry['episode'], episode_title, show_name,
            entry.get('genre'),
            names.resolution_for(stream['video']['width']),
            stream['audio']['channels'], stream['audio']['codec'])
        folder = os.path.dirname(path)
        extension = os.path.splitext(path)[1]
        target = os.path.join(folder, wanted + extension)
        if target == path:
            return path
        target = names.free_path(folder, wanted + extension)
        try:
            os.rename(path, target)
            if os.path.exists(nfo_path):
                os.rename(nfo_path, os.path.splitext(target)[0] + '.nfo')
        except OSError as exc:
            self.log(u'cannot rename to the long form: %s' % exc)
            return path
        return target

    # -- a pass ------------------------------------------------------------

    def run(self):
        """File everything that is waiting. Returns a Report.

        The show list is written once at the end rather than after each file,
        which is the script's behaviour, and is why a pass that is interrupted
        may leave a file filed under a number the list does not know about.
        """
        report = Report()
        if not self.source or not os.path.isdir(self.source):
            self.log(u'no source folder: %s' % self.source)
            return report
        if not self.destination:
            self.log(u'no destination folder')
            return report

        data = shows_lib.load(self.profile, self.episodes_per_season)
        waiting = self.videos()
        report.seen = len(waiting)

        for path in waiting:
            if not self.has_settled(path):
                self.log(u'still arriving: %s' % os.path.basename(path))
                report.seen -= 1
                continue
            try:
                self.process(path, data, report)
            except Exception as exc:              # noqa: BLE001
                # One unreadable file must not end the pass. The script let an
                # exception out and stopped, which on a folder of fifty
                # downloads means the other forty-nine wait for someone to
                # notice.
                self.log(u'failed on %s: %s' % (os.path.basename(path), exc))
                report.failed.append(path)

        if report.filed or report.new_shows:
            shows_lib.save(self.profile, data)
        return report
