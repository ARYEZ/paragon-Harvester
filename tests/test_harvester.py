# -*- coding: utf-8 -*-
"""
Paragon Harvester - the tests.

    python3 tests/test_harvester.py

The add-on runs on Python 2.7 inside Kodi and these run on Python 3 outside
it, which sounds like a contradiction and is the arrangement the rest of the
Paragon add-ons use. What the tests hold is behaviour, and behaviour is the
same in both; what differs between the two interpreters is caught by
check_py2.py, which reads every shipped file for constructs 2.7 cannot parse.

Kodi itself is a set of stubs under tests/kodistubs, so anything that reaches
for xbmc gets an answer a test can see.
"""

from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'kodistubs'))
sys.path.insert(0, os.path.join(ROOT, 'resources', 'lib'))
sys.path.insert(0, ROOT)          # default.py and service.py

import xbmc
import xbmcaddon
import xbmcgui

import harvest
import names
import nfo
import shows
import text


class FakeProbe(object):
    """yt-dlp and ffprobe, answering whatever a test needs them to.

    Neither program is installed where the tests run, and pointing the engine
    at the real ones would make every test a network call. The engine takes
    the probe as an argument for exactly this reason.
    """

    def __init__(self, metadata=None, found_id=None, stream=None):
        self.answers = metadata or {}
        self.found_id = found_id
        self.stream = stream
        self.searched = []
        self.looked_up = []

    def search(self, query, channel=None):
        self.searched.append((query, channel))
        return self.found_id

    def metadata(self, video_id):
        self.looked_up.append(video_id)
        return self.answers.get(video_id)

    def stream_info(self, path):
        return self.stream


class RecordingAsker(harvest.Asker):
    """Stands in for the dialog, and writes down what it was asked."""

    def __init__(self, summary=None, genre=None, channel=None):
        self.asked = []
        self.answer = (summary, genre, channel)

    def about_new_show(self, show_key, suggested_summary, default_genre,
                       default_channel):
        self.asked.append(show_key)
        summary, genre, channel = self.answer
        return (summary or suggested_summary, genre or default_genre,
                channel or default_channel)


class TestCleaningATitle(unittest.TestCase):
    """What comes off a YouTube title, and what must not."""

    def test_the_decoration_comes_off(self):
        self.assertEqual(
            text.clean_episode_title('Midnight Drive (Official Music Video)'),
            'Midnight Drive')
        self.assertEqual(
            text.clean_episode_title('Midnight Drive [HD]'), 'Midnight Drive')
        self.assertEqual(
            text.clean_episode_title('Midnight Drive - Official Video'),
            'Midnight Drive')

    def test_the_longest_suffix_wins(self):
        """Otherwise " official lyric video" leaves " official" behind."""
        self.assertEqual(
            text.clean_episode_title('Runaway official lyric video'),
            'Runaway')

    def test_credits_are_cut_at_the_marker(self):
        self.assertEqual(
            text.clean_episode_title('Runaway ft. Someone Else'), 'Runaway')
        self.assertEqual(
            text.clean_episode_title('Runaway FEAT. Someone'), 'Runaway')

    def test_a_title_that_cleans_to_nothing_is_kept(self):
        """Every rule here can go too far, so there is a floor under them."""
        self.assertEqual(text.clean_episode_title('(Official Video)'),
                         '(Official Video)')
        self.assertEqual(text.clean_episode_title('Go'), 'Go')

    def test_nothing_in_stays_nothing_out(self):
        self.assertEqual(text.clean_episode_title(''), '')
        self.assertIsNone(text.clean_episode_title(None))


class TestWhatKodisDatabaseCanHold(unittest.TestCase):
    """Kodi's MySQL tables are plain utf8: three bytes, no more."""

    def test_an_emoji_is_dropped(self):
        self.assertEqual(text.strip_wide('a \U0001F319 b'), 'a  b')

    def test_so_is_half_of_one(self):
        """The bug the port had to answer for.

        Python 2 on Windows is a narrow build, so an emoji arrives as two
        surrogate characters, both below U+FFFF. A test for "above U+FFFF"
        passes them through and writes a broken pair into the NFO, which is
        not better than the emoji: it is worse.
        """
        broken = 'a' + chr(0xD83C) + chr(0xDF19) + 'b'
        self.assertEqual(text.strip_wide(broken), 'ab')

    def test_ordinary_symbols_are_kept(self):
        """Three bytes is plenty for these, and they carry meaning."""
        self.assertEqual(text.strip_wide('Café ± 5° «quoted»'),
                         'Café ± 5° «quoted»')


class TestCleaningADescription(unittest.TestCase):
    """A YouTube description is a paragraph followed by advertising."""

    def setUp(self):
        self.fallback = 'Some Episode from Some Channel'

    def clean(self, description):
        return text.clean_description(description, 'Some Episode',
                                      'Some Channel')

    def test_the_writing_is_kept_and_the_advertising_is_not(self):
        got = self.clean('A quiet film about the sea.\n'
                         'Patreon: example.com/x\n'
                         'More writing that came after the advertising.')
        self.assertEqual(got, 'A quiet film about the sea.')

    def test_advertising_before_the_writing_is_stepped_over(self):
        """Stopping there would throw the description away whole."""
        got = self.clean('Subscribe!\nA quiet film about the sea.')
        self.assertEqual(got, 'A quiet film about the sea.')

    def test_links_and_rules_and_lyrics_are_dropped(self):
        for noise in ('https://example.com/thing',
                      'bit.ly/thing',
                      '▬▬▬▬▬▬▬▬▬▬',
                      '[Verse 1]',
                      'Chorus 2',
                      '» something «'):
            got = self.clean(noise + '\nA quiet film about the sea.')
            self.assertEqual(got, 'A quiet film about the sea.', noise)

    def test_a_description_with_nothing_in_it_falls_back(self):
        self.assertEqual(self.clean(''), self.fallback)
        self.assertEqual(self.clean('Subscribe!'), self.fallback)
        self.assertEqual(self.clean('Too short'), self.fallback)

    def test_a_long_description_is_cut_to_the_limit(self):
        got = self.clean('word ' * 400)
        self.assertEqual(len(got), text.PLOT_LIMIT)
        self.assertTrue(got.endswith('...'))

    def test_an_emoji_in_the_description_does_not_reach_the_plot(self):
        got = self.clean('A quiet film about the sea \U0001F319 and the sky.')
        self.assertNotIn('\U0001F319', got)


class TestThePlot(unittest.TestCase):
    """Best source first, and never empty."""

    def test_the_description_wins_when_there_is_one(self):
        self.assertEqual(
            text.generate_plot('Show', 'Episode', 'The summary.',
                               'What the uploader wrote about it.'),
            'What the uploader wrote about it.')

    def test_the_summary_is_next(self):
        self.assertEqual(text.generate_plot('Show', 'Episode', 'The summary.'),
                         'The summary. This one is called Episode.')

    def test_and_there_is_always_something(self):
        self.assertEqual(text.generate_plot('Show', 'Episode'),
                         "Episode 'Episode' of Show.")

    def test_a_scrap_of_a_description_is_not_a_plot(self):
        """Ten characters is the line the script drew."""
        self.assertEqual(text.generate_plot('Show', 'Episode', 'The summary.',
                                            'Short'),
                         'The summary. This one is called Episode.')


class TestNamingAShow(unittest.TestCase):
    def test_a_filename_loses_what_a_filename_may_not_hold(self):
        self.assertEqual(text.sanitise_filename('AC/DC: Live? <yes>'),
                         'ACDC Live yes')

    def test_a_summary_is_suggested_from_the_name(self):
        self.assertIn('musical act', text.suggest_show_summary('The Band'))
        self.assertIn('comedic', text.suggest_show_summary('Comedy Hour'))
        self.assertIn('documentary', text.suggest_show_summary('Nature Watch'))
        self.assertIn('captivating', text.suggest_show_summary('Lofi Girl'))


class TestTheNfoText(unittest.TestCase):
    """What Kodi reads. Built as text, so a test can read it too."""

    def episode(self, **kwargs):
        import xml.etree.ElementTree as ET
        fields = dict(show_name='Some Show', episode_title='Some Episode',
                      season=1, episode=2, file_path='/x/01x02 - Thing.mp4',
                      genre='Music', date_added='2000-01-01',
                      series_summary='About the show.')
        fields.update(kwargs)
        body = nfo.episode_nfo(**fields)
        return body, ET.fromstring(body.encode('utf-8'))

    def test_it_is_valid_xml_with_the_fields_kodi_wants(self):
        body, root = self.episode()
        self.assertEqual(root.tag, 'episodedetails')
        self.assertEqual(root.findtext('season'), '1')
        self.assertEqual(root.findtext('episode'), '2')
        self.assertEqual(root.findtext('title'), 'Some Episode')
        self.assertEqual(root.findtext('showtitle'), 'Some Show')
        self.assertEqual(root.findtext('file'), '01x02 - Thing.mp4')

    def test_an_ampersand_in_a_title_does_not_break_it(self):
        """The reason every field goes through escaping rather than most."""
        _body, root = self.episode(show_name='Fish & Chips',
                                   episode_title='This & That')
        self.assertEqual(root.findtext('showtitle'), 'Fish & Chips')
        self.assertEqual(root.findtext('title'), 'This & That')

    def test_an_emoji_in_a_plot_does_not_reach_the_file(self):
        _body, root = self.episode(description='A film \U0001F319 at sea and '
                                               'what happened after it')
        self.assertNotIn('\U0001F319', root.findtext('plot'))

    def test_the_upload_date_becomes_the_aired_date(self):
        _body, root = self.episode(aired='2019-04-01')
        self.assertEqual(root.findtext('aired'), '2019-04-01')
        self.assertEqual(root.findtext('dateadded'), '2000-01-01')

    def test_without_ffprobe_the_stream_details_are_a_shape_not_a_claim(self):
        _body, root = self.episode()
        self.assertEqual(root.findtext('.//width'), '1920')
        self.assertEqual(root.findtext('.//codec'), 'h264')

    def test_a_show_nfo_carries_the_summary_and_genre(self):
        import xml.etree.ElementTree as ET
        body = nfo.tvshow_nfo('Some Show', 'Music', 'About the show.',
                              '2026-01-01T00:00:00Z')
        root = ET.fromstring(body.encode('utf-8'))
        self.assertEqual(root.tag, 'tvshow')
        self.assertEqual(root.findtext('title'), 'Some Show')
        self.assertEqual(root.findtext('plot'), 'About the show.')
        self.assertEqual(root.findtext('genre'), 'Music')


class TestRepairingNfos(unittest.TestCase):
    """For a library that already has emoji in it."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, body):
        path = os.path.join(self.root, rel)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        handle = open(path, 'w', encoding='utf-8')
        handle.write(body)
        handle.close()
        return path

    def test_only_the_files_that_needed_it_are_touched(self):
        bad = self.write('Show/01x01.nfo', '<plot>sea \U0001F319 sky</plot>')
        good = self.write('Show/01x02.nfo', '<plot>sea and sky</plot>')

        changed = nfo.sanitise(self.root)

        self.assertEqual(changed, [bad])
        self.assertEqual(open(bad, encoding='utf-8').read(),
                         '<plot>sea  sky</plot>')
        self.assertEqual(open(good, encoding='utf-8').read(),
                         '<plot>sea and sky</plot>')

    def test_anything_that_is_not_an_nfo_is_left_alone(self):
        self.write('Show/01x01.mp4', 'sea \U0001F319 sky')
        self.assertEqual(nfo.sanitise(self.root), [])


class TestTheShowList(unittest.TestCase):
    """Where the numbering lives."""

    def setUp(self):
        self.profile = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.profile, ignore_errors=True)

    def test_a_show_is_filed_under_one_name_however_it_is_typed(self):
        self.assertEqual(shows.key_for('lofi girl'), 'Lofi Girl')
        self.assertEqual(shows.key_for('  LOFI GIRL '), 'Lofi Girl')

    def test_a_new_show_starts_at_one_by_one(self):
        data = {}
        entry = shows.register(data, 'Lofi Girl', 'About it.', 'Music', None)
        self.assertEqual((entry['season'], entry['episode']), (1, 1))
        self.assertEqual(entry['summary'], 'About it.')

    def test_the_next_episode_counts_on_and_the_season_rolls(self):
        data = {}
        shows.register(data, 'Show')
        for _ in range(23):
            entry = shows.advance(data, 'Show', 24)
        self.assertEqual((entry['season'], entry['episode']), (1, 24))

        entry = shows.advance(data, 'Show', 24)
        self.assertEqual((entry['season'], entry['episode']), (2, 1))

    def test_a_show_that_is_not_there_is_registered_rather_than_lost(self):
        data = {}
        entry = shows.advance(data, 'Show')
        self.assertEqual((entry['season'], entry['episode']), (1, 1))

    def test_it_survives_being_written_and_read_back(self):
        data = {}
        shows.register(data, 'Café Show', 'About it.', 'Music', '@someone')
        shows.advance(data, 'Café Show')

        self.assertTrue(shows.save(self.profile, data))
        back = shows.load(self.profile)

        self.assertEqual(back['Café Show']['episode'], 2)
        self.assertEqual(back['Café Show']['channel'], '@someone')

    def test_the_oldest_files_still_read(self):
        """A list is what a version before the summaries wrote."""
        handle = open(shows.store_path(self.profile), 'w', encoding='utf-8')
        handle.write('{"Old Show": [3, 7, "Comedy"]}')
        handle.close()

        back = shows.load(self.profile)

        self.assertEqual(back['Old Show']['season'], 3)
        self.assertEqual(back['Old Show']['episode'], 7)
        self.assertEqual(back['Old Show']['genre'], 'Comedy')

    def test_a_store_that_cannot_be_read_is_not_a_store_that_is_wiped(self):
        handle = open(shows.store_path(self.profile), 'w', encoding='utf-8')
        handle.write('{ this is not json')
        handle.close()

        self.assertEqual(shows.load(self.profile), {})
        self.assertTrue(os.path.isfile(shows.store_path(self.profile)))

    def test_a_reset_keeps_the_channel_it_took_work_to_find(self):
        data = {}
        shows.register(data, 'Show', 'About it.', 'Music', '@someone')
        shows.advance(data, 'Show')

        entry = shows.reset(data, 'Show', 'New summary.', 'Jazz')

        # Zero, so that the next file filed becomes episode one.
        self.assertEqual((entry['season'], entry['episode']), (1, 0))
        self.assertEqual(shows.advance(data, 'Show')['episode'], 1)
        self.assertEqual(entry['channel'], '@someone')
        self.assertEqual(entry['summary'], 'New summary.')


class TestReadingAFile(unittest.TestCase):
    """Which show a video belongs to, and what the episode is called."""

    def test_an_id_is_found_in_a_downloaded_name(self):
        self.assertEqual(names.video_id('Sunset [dQw4w9WgXcQ].mp4'),
                         'dQw4w9WgXcQ')
        self.assertIsNone(names.video_id('Sunset.mp4'))
        self.assertIsNone(names.video_id('Sunset [tooshort].mp4'))

    def test_a_loose_file_is_read_apart_at_the_dash(self):
        self.assertEqual(names.split_filename('Lofi Girl - Sunset Drive.mp4'),
                         ('Lofi Girl', 'Sunset Drive'))

    def test_a_name_that_cannot_be_read_apart_says_so(self):
        self.assertEqual(names.split_filename('video.mp4'), (None, None))

    def test_the_long_name_carries_the_whole_episode(self):
        self.assertEqual(
            names.extended_name(1, 2, 'Sunset Drive', 'Lofi Girl', 'Music',
                                '1080', 2, 'aac'),
            '01x02 - Sunset Drive - Lofi Girl - Music - 1080 - 2 - AAC - None')

    def test_a_show_with_no_genre_is_still_named(self):
        got = names.extended_name(1, 1, 'A', 'B', None, '720', 2, 'aac')
        self.assertIn(' - Unknown - ', got)

    def test_the_resolution_is_read_off_the_video(self):
        self.assertEqual(names.resolution_for(3840), '2160')
        self.assertEqual(names.resolution_for(1920), '1080')
        self.assertEqual(names.resolution_for(1280), '720')
        self.assertEqual(names.resolution_for(640), '480')
        self.assertEqual(names.resolution_for(None), '480')


class TestAHarvest(unittest.TestCase):
    """A folder of downloads in, a library of shows out."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.source = os.path.join(self.root, 'vault')
        self.dest = os.path.join(self.root, 'shows')
        self.profile = os.path.join(self.root, 'profile')
        for path in (self.source, self.dest, self.profile):
            os.makedirs(path)
        self.probe = FakeProbe()
        self.asker = RecordingAsker()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def drop(self, rel, body='video'):
        """Put a file in the source folder, as a download would."""
        path = os.path.join(self.source, rel)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        handle = open(path, 'w')
        handle.write(body)
        handle.close()
        return path

    def harvester(self, **kwargs):
        fields = dict(source=self.source, destination=self.dest,
                      profile=self.profile, probe=self.probe,
                      asker=self.asker)
        fields.update(kwargs)
        return harvest.Harvester(**fields)

    def filed(self):
        """Everything that ended up in the destination, relative to it."""
        out = []
        for here, _dirs, files in os.walk(self.dest):
            for name in files:
                out.append(os.path.relpath(os.path.join(here, name),
                                           self.dest))
        return sorted(out)

    def test_a_loose_file_is_filed_under_its_show(self):
        self.drop('Lofi Girl - Sunset Drive.mp4')

        report = self.harvester().run()

        self.assertEqual(report.count, 1)
        self.assertEqual(self.filed(), [
            os.path.join('Lofi Girl', '01x01 - Sunset Drive - Lofi Girl - '
                                      'Unknown - 1080 - 2 - AAC - None.mp4'),
            os.path.join('Lofi Girl', '01x01 - Sunset Drive - Lofi Girl - '
                                      'Unknown - 1080 - 2 - AAC - None.nfo'),
            os.path.join('Lofi Girl', 'tvshow.nfo'),
        ])
        self.assertFalse(os.listdir(self.source))

    def test_a_file_in_a_subfolder_takes_the_folder_as_its_show(self):
        self.drop(os.path.join('Nature Watch', 'Deep Sea Vents.mp4'))

        self.harvester().run()

        self.assertTrue(any(name.startswith('Nature Watch' + os.sep)
                            for name in self.filed()), self.filed())

    def test_a_name_it_cannot_read_is_left_where_it_is(self):
        path = self.drop('video.mp4')

        report = self.harvester().run()

        self.assertEqual(report.count, 0)
        self.assertEqual(report.skipped, [path])
        self.assertTrue(os.path.exists(path))

    def test_the_numbering_counts_on_across_passes(self):
        self.drop('Lofi Girl - One.mp4')
        self.harvester().run()
        self.drop('Lofi Girl - Two.mp4')

        self.harvester().run()

        self.assertTrue(any('01x02 - Two' in name for name in self.filed()),
                        self.filed())

    def test_a_new_show_is_asked_about_once(self):
        self.drop('Lofi Girl - One.mp4')
        self.drop('Lofi Girl - Two.mp4')

        report = self.harvester().run()

        self.assertEqual(self.asker.asked, ['Lofi Girl'])
        self.assertEqual(report.new_shows, ['Lofi Girl'])

    def test_what_the_asker_says_is_what_the_show_becomes(self):
        self.drop('Lofi Girl - One.mp4')
        asker = RecordingAsker('A quiet channel.', 'Ambient', '@lofigirl')

        self.harvester(asker=asker).run()

        entry = shows.load(self.profile)['Lofi Girl']
        self.assertEqual(entry['summary'], 'A quiet channel.')
        self.assertEqual(entry['genre'], 'Ambient')
        self.assertEqual(entry['channel'], '@lofigirl')

    def test_an_id_in_the_name_is_looked_up_rather_than_searched(self):
        self.drop('Lofi Girl - Sunset [dQw4w9WgXcQ].mp4')
        self.probe.answers['dQw4w9WgXcQ'] = {
            'description': 'A long quiet mix recorded beside the sea.',
            'upload_date': '20190401', 'uploader': 'Lofi Girl'}

        self.harvester().run()

        self.assertEqual(self.probe.looked_up, ['dQw4w9WgXcQ'])
        self.assertEqual(self.probe.searched, [])

    def test_without_an_id_the_search_is_scoped_to_the_channel(self):
        self.drop('Lofi Girl - Sunset.mp4')
        asker = RecordingAsker(channel='@lofigirl')

        self.harvester(asker=asker).run()

        self.assertEqual(self.probe.searched, [('Lofi Girl Sunset',
                                                '@lofigirl')])

    def test_what_youtube_said_ends_up_in_the_plot(self):
        import xml.etree.ElementTree as ET

        self.drop('Lofi Girl - Sunset [dQw4w9WgXcQ].mp4')
        self.probe.answers['dQw4w9WgXcQ'] = {
            'description': 'A long quiet mix recorded beside the sea.',
            'upload_date': '20190401', 'uploader': 'Lofi Girl'}

        self.harvester().run()

        nfo_path = [os.path.join(self.dest, name) for name in self.filed()
                    if name.endswith('.nfo') and 'tvshow' not in name][0]
        root = ET.parse(nfo_path).getroot()
        self.assertEqual(root.findtext('plot'),
                         'A long quiet mix recorded beside the sea.')
        self.assertEqual(root.findtext('aired'), '2019-04-01')

    def test_a_file_does_not_land_on_one_already_there(self):
        """Which happens after a show is started over.

        Two copies in a row do not collide: the numbering moves on and the
        names differ. Reset the show and the numbering goes back to 01x01,
        which is the same name as the file already filed under it.
        """
        self.drop('Lofi Girl - Sunset.mp4')
        self.harvester().run()

        data = shows.load(self.profile)
        shows.reset(data, 'Lofi Girl')
        shows.save(self.profile, data)
        self.drop('Lofi Girl - Sunset.mp4')

        self.harvester().run()

        videos = [name for name in self.filed() if name.endswith('.mp4')]
        self.assertEqual(len(videos), 2, videos)
        self.assertTrue(all('01x01' in name for name in videos), videos)
        self.assertTrue(any(name.endswith('_1.mp4') for name in videos),
                        videos)

    def test_a_file_still_being_written_is_left_for_next_time(self):
        path = self.drop('Lofi Girl - Sunset.mp4')

        report = self.harvester(settle_seconds=300).run()

        self.assertEqual(report.count, 0)
        self.assertEqual(report.seen, 0)
        self.assertTrue(os.path.exists(path))

    def test_one_bad_file_does_not_end_the_pass(self):
        """Fifty downloads and one of them unreadable is not fifty waiting."""
        self.drop('Lofi Girl - One.mp4')
        self.drop('Lofi Girl - Two.mp4')

        class Angry(FakeProbe):
            def metadata(self, video_id):
                raise RuntimeError('yt-dlp fell over')

            def search(self, query, channel=None):
                if 'One' in query:
                    raise RuntimeError('yt-dlp fell over')
                return None

        report = self.harvester(probe=Angry()).run()

        self.assertEqual(report.count, 1)
        self.assertEqual(len(report.failed), 1)

    def test_nothing_to_do_is_not_an_error(self):
        report = self.harvester().run()
        self.assertEqual(report.seen, 0)
        self.assertEqual(report.describe(), 'Nothing to file')

    def test_a_source_folder_that_is_not_there_is_not_an_error(self):
        report = self.harvester(source=os.path.join(self.root, 'nope')).run()
        self.assertEqual(report.count, 0)


class TestTheAddonItself(unittest.TestCase):
    """The parts that only exist inside Kodi."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.source = os.path.join(self.root, 'vault')
        self.dest = os.path.join(self.root, 'shows')
        for path in (self.source, self.dest):
            os.makedirs(path)
        xbmcaddon.reset({'source_folder': self.source,
                         'dest_folder': self.dest,
                         'show_notifications': 'true'})
        # A profile of this test's own. The stub's default is one directory
        # shared by every test, so the show list written by one of them was
        # still there for the next, and a new show was not new any more.
        xbmcaddon._INFO['profile'] = os.path.join(self.root, 'profile')
        xbmcgui.reset()
        xbmc.reset_rpc()
        for name in ('addon_utils', 'gui', 'library', 'probe'):
            if name in sys.modules:
                del sys.modules[name]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        xbmcaddon.reset()
        xbmcgui.reset()

    def drop(self, name):
        """A download that finished ten minutes ago.

        Written and then aged, because the harvester leaves a file alone
        until it has stopped changing and a file written this second has
        not. The settle time is a setting, and using it here rather than
        turning it off keeps these tests on the same path as a real pass.
        """
        path = os.path.join(self.source, name)
        handle = open(path, 'w')
        handle.write('video')
        handle.close()
        old = time.time() - 600
        os.utime(path, (old, old))
        return path

    def test_the_arguments_a_keymap_passes_are_read(self):
        import default
        self.assertEqual(
            default.parse_args(['default.py', 'action=run']),
            {'action': 'run'})
        self.assertEqual(default.parse_args(['default.py', 'rubbish']), {})

    def test_the_folders_have_to_be_set_before_anything_runs(self):
        import gui
        self.assertIsNone(gui.folders_missing())

        xbmcaddon.SETTINGS['source_folder'] = ''
        self.assertIn('downloads arrive', gui.folders_missing())

        xbmcaddon.SETTINGS['source_folder'] = self.source
        xbmcaddon.SETTINGS['dest_folder'] = ''
        self.assertIn('shows are filed', gui.folders_missing())

    def test_a_pass_with_nothing_set_up_says_so_and_stops(self):
        import gui
        xbmcaddon.SETTINGS['source_folder'] = ''

        self.assertIsNone(gui.run_pass(None))

        self.assertTrue([m for _h, m in xbmcgui.NOTIFICATIONS
                         if 'downloads arrive' in m])

    def test_a_pass_tells_kodi_what_changed(self):
        import gui
        self.drop('Lofi Girl - One.mp4')

        report = gui.run_pass(None)

        self.assertEqual(report.count, 1)
        scans = [call for call in xbmc.rpc_calls
                 if call.get('method') == 'VideoLibrary.Scan']
        self.assertEqual(len(scans), 1)

    def test_a_pass_that_filed_nothing_does_not_scan(self):
        """A scan of a library this has been filling for a year is minutes."""
        import gui

        gui.run_pass(None)

        self.assertEqual([call for call in xbmc.rpc_calls
                          if call.get('method') == 'VideoLibrary.Scan'], [])

    def test_a_show_set_up_from_the_defaults_is_reported(self):
        """Nobody was asked, so somebody has to be told."""
        import gui
        self.drop('Lofi Girl - One.mp4')

        gui.run_pass(None)

        self.assertTrue([m for _h, m in xbmcgui.NOTIFICATIONS
                         if 'Lofi Girl' in m], xbmcgui.NOTIFICATIONS)

    def test_the_new_show_dialog_keeps_the_suggestion_when_it_is_cancelled(self):
        """Back means "that will do", not "leave it empty"."""
        import gui
        xbmcgui.INPUT_QUEUE.extend(['', '', ''])

        summary, genre, channel = gui.Dialogs().about_new_show(
            'Lofi Girl', 'A quiet channel.', 'Music', '@lofigirl')

        self.assertEqual(summary, 'A quiet channel.')
        self.assertEqual(genre, 'Music')
        self.assertEqual(channel, '@lofigirl')

    def test_what_is_typed_into_it_wins(self):
        import gui
        xbmcgui.INPUT_QUEUE.extend(['Mine.', 'Jazz', '@someone'])

        self.assertEqual(
            gui.Dialogs().about_new_show('Show', 'Suggested.', 'Music', None),
            ('Mine.', 'Jazz', '@someone'))

    def test_a_scan_names_the_folder_with_a_separator_on_it(self):
        """Kodi answers a directory without one by scanning nothing."""
        import library

        library.scan('/media/shows')

        scans = [call for call in xbmc.rpc_calls
                 if call.get('method') == 'VideoLibrary.Scan']
        self.assertEqual(scans[0]['params']['directory'], '/media/shows/')

    def test_the_service_waits_for_its_interval(self):
        import service
        self.assertFalse(service.due(30, 15))
        self.assertFalse(service.due(14 * 60, 15))
        self.assertTrue(service.due(15 * 60, 15))

    def test_an_interval_of_nothing_is_still_an_interval(self):
        """A slider at zero would be a harvest every tick."""
        import service
        self.assertFalse(service.due(30, 0))
        self.assertTrue(service.due(60, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
