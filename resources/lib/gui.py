# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The part a person touches: the menu, and the one question the harvester asks.

The script asked sixteen questions at a console. Most of them were about a
show it had never seen, and the rest were asked once per run. Here a known
show goes through without a word and only a new one opens a dialog, which is
the difference between filing twenty videos and answering sixty prompts.
"""

import os

import xbmcgui

import addon_utils as utils
import harvest
import library
import nfo
import probe as probe_lib
import shows as shows_lib
import text as text_lib

BACK = -1


def _dialog():
    return xbmcgui.Dialog()


def _select(heading, options):
    """Dialog().select, answering BACK when it is cancelled."""
    choice = _dialog().select(heading, options)
    return BACK if choice is None or choice < 0 else choice


class Dialogs(harvest.Asker):
    """The engine's one question, asked with Kodi's keyboard.

    Cancelling any part of it keeps the suggestion rather than emptying the
    field: a show with no summary shows a blank page in Kodi, and somebody
    who pressed Back meant "that will do", not "leave it empty".
    """

    def about_new_show(self, show_key, suggested_summary, default_genre,
                       default_channel):
        heading = 'New show: %s' % show_key
        summary = _dialog().input('%s - what is it?' % heading,
                                  suggested_summary)
        summary = (summary or '').strip() or suggested_summary

        genre = _dialog().input('%s - genre' % heading, default_genre or '')
        genre = (genre or '').strip() or default_genre

        channel = _dialog().input(
            '%s - YouTube channel, blank to search all of YouTube' % heading,
            default_channel or '')
        channel = (channel or '').strip() or default_channel

        return summary, genre, channel


def build_probe():
    return probe_lib.Probe(ytdlp=utils.get_setting('ytdlp_path', 'yt-dlp'),
                           ffprobe=utils.get_setting('ffprobe_path',
                                                     'ffprobe'),
                           timeout=utils.get_int('lookup_seconds', 30))


def build_harvester(asker=None):
    """A harvester wired up from the settings."""
    return harvest.Harvester(
        source=utils.get_setting('source_folder', ''),
        destination=utils.get_setting('dest_folder', ''),
        profile=utils.profile_dir(),
        probe=build_probe(),
        asker=asker,
        default_genre=utils.get_setting('default_genre', ''),
        default_channel=utils.get_setting('default_channel', ''),
        episodes_per_season=utils.get_int('episodes_per_season', 24),
        settle_seconds=utils.get_int('settle_seconds', 30),
        log=utils.log)


def folders_missing():
    """The message to show when the folders are not set up, or None."""
    source = utils.get_setting('source_folder', '')
    destination = utils.get_setting('dest_folder', '')
    if not source or not os.path.isdir(source):
        return 'Set where downloads arrive, in settings'
    if not destination:
        return 'Set where shows are filed, in settings'
    return None


def run_pass(asker=None):
    """One harvest, with a progress dialog and a report at the end."""
    problem = folders_missing()
    if problem:
        utils.force_notify(problem)
        return None

    harvester = build_harvester(asker)
    progress = xbmcgui.DialogProgressBG()
    try:
        progress.create(utils.ADDON_NAME, 'Looking for new videos')
    except Exception:
        progress = None

    try:
        report = harvester.run()
    finally:
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass

    utils.notify(report.describe())
    if report.filed:
        library.scan(utils.get_setting('dest_folder', ''))
    if report.new_shows and asker is None:
        # Nobody was asked, so somebody should be told: a show set up from the
        # defaults has a guessed summary and no channel.
        utils.force_notify('Set up from defaults: %s'
                           % ', '.join(report.new_shows))
    return report


class ControlPanel(object):
    """The add-on's menus."""

    def run(self):
        while self.main_menu():
            pass

    def main_menu(self):
        """The one screen. True to stay open."""
        rows = [
            ('Run a pass now', self.harvest_now),
            ('What it knows', self.show_list),
            ('Start a show over...', self.reset_show),
            ('Clean up NFOs', self.sanitise),
            ('Settings', self.settings),
        ]
        choice = _select(utils.ADDON_NAME, [label for label, _f in rows])
        if choice == BACK:
            return False
        rows[choice][1]()
        return True

    def harvest_now(self):
        asker = Dialogs() if utils.get_bool('ask_about_new_shows', True) \
            else None
        run_pass(asker)

    def show_list(self):
        """Every show it has filed, and where its numbering is up to."""
        data = shows_lib.load(utils.profile_dir())
        if not data:
            utils.force_notify('Nothing filed yet')
            return
        rows = []
        for key in sorted(data):
            entry = data[key]
            rows.append('%s  -  %02dx%02d%s'
                        % (key, entry['season'], entry['episode'],
                           '  -  %s' % entry['genre'] if entry['genre']
                           else ''))
        _select('Shows', rows)

    def reset_show(self):
        """Scrap what is known about a show and start its numbering again.

        The channel is kept unless it is changed here, because it is the field
        that took looking up and the reason to reset is nearly always the
        numbering.
        """
        profile = utils.profile_dir()
        data = shows_lib.load(profile)
        if not data:
            utils.force_notify('Nothing filed yet')
            return
        names = sorted(data)
        choice = _select('Start which show over?', names)
        if choice == BACK:
            return
        show_key = names[choice]
        entry = data[show_key]

        if not _dialog().yesno(
                show_key,
                'Start %s again at 01x01?' % show_key,
                'It is at %02dx%02d now.' % (entry['season'],
                                             entry['episode']),
                'Files already filed are not touched.'):
            return

        suggested = entry.get('summary') or \
            text_lib.suggest_show_summary(show_key)
        summary = _dialog().input('What is %s?' % show_key, suggested)
        summary = (summary or '').strip() or suggested
        genre = _dialog().input('Genre for %s' % show_key,
                                entry.get('genre') or '')
        channel = entry.get('channel')
        if channel and not _dialog().yesno(
                show_key, 'Keep the channel it matches?', channel):
            channel = _dialog().input('YouTube channel for %s' % show_key,
                                      '').strip() or None

        shows_lib.reset(data, show_key, summary, (genre or '').strip() or None,
                        channel)
        if shows_lib.save(profile, data):
            utils.notify('%s starts again at 01x01' % show_key)
        else:
            utils.force_notify('Could not write the show list')

    def sanitise(self):
        """Strip what Kodi cannot store from NFOs that already exist.

        The repair job for a library that will not scan: Kodi's MySQL tables
        are plain utf8 and an emoji in a plot fails the scan with error 1366,
        which shows up as an episode that simply never appears.
        """
        destination = utils.get_setting('dest_folder', '')
        if not destination or not os.path.isdir(destination):
            utils.force_notify('Set where shows are filed, in settings')
            return
        if not _dialog().yesno(utils.ADDON_NAME,
                               'Read every NFO under %s' % destination,
                               'and take out what Kodi cannot store?'):
            return

        changed = nfo.sanitise(destination)
        if not changed:
            utils.notify('Nothing needed cleaning')
            return
        utils.notify('%d NFO(s) cleaned' % len(changed))
        library.refresh_folders(sorted(set(os.path.dirname(path)
                                           for path in changed)))

    def settings(self):
        utils.ADDON.openSettings()
