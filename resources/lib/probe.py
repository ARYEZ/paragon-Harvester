# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The two outside programs: yt-dlp for what YouTube knows, ffprobe for what the
file itself says.

Both are optional. Without ffprobe the NFO gets a default shape and Kodi
works the real numbers out when it scans. Without yt-dlp there is no
metadata at all and an episode keeps its generated plot, which is the whole
reason the add-on asks to be installed on the box that has yt-dlp.

Nothing here imports Kodi, so a test drives it by pointing `runner` at a fake
instead of at subprocess.
"""

import json
import subprocess
import threading

import compat

DEFAULT_TIMEOUT = 30

# Tabs a channel URL might be sitting on when it is pasted, which have to come
# off before /search can go on the end.
CHANNEL_TABS = ('/videos', '/featured', '/streams', '/shorts', '/playlists',
                '/community', '/about', '/search')


def run(command, timeout=DEFAULT_TIMEOUT):
    """Run `command` and give back (ok, stdout). Never raises.

    Python 2.7's subprocess has no timeout, and a yt-dlp that sits waiting on
    a network that is not there would hold a Kodi service thread for as long
    as it liked. So the wait is done with a timer that kills the process,
    which is what subprocess.run(timeout=...) does for the script on Python 3.
    """
    process = None
    timer = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    except (OSError, ValueError):
        # Not installed, or not where the setting says it is.
        return False, ''

    def give_up():
        try:
            process.kill()
        except (OSError, AttributeError):
            pass

    try:
        timer = threading.Timer(timeout, give_up)
        timer.start()
        out, _err = process.communicate()
    except (OSError, ValueError):
        return False, ''
    finally:
        if timer is not None:
            timer.cancel()

    return process.returncode == 0, compat.as_text(out)


class Probe(object):
    """yt-dlp and ffprobe, as far as this add-on needs them.

    The programs are named rather than assumed so a box that keeps them
    somewhere odd can say where in the settings, and `runner` is an argument
    so the tests can answer for both without either being installed.
    """

    def __init__(self, ytdlp='yt-dlp', ffprobe='ffprobe',
                 timeout=DEFAULT_TIMEOUT, runner=None):
        self.ytdlp = ytdlp or 'yt-dlp'
        self.ffprobe = ffprobe or 'ffprobe'
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.run = runner or run

    # -- YouTube -----------------------------------------------------------

    def channel_search_url(self, channel, query):
        """A channel's own search page, from a link, an @handle or an id.

        Scoping the search to the channel is what stops a title like "Sunset"
        matching whatever the whole of YouTube thinks is the best Sunset. It
        is the difference between the right uploader and a stranger's video
        in your library under your show's name.
        """
        channel = (channel or '').strip()
        wanted = compat.quoted(query)

        if channel.startswith(('http://', 'https://')):
            base = channel.rstrip('/')
            for tab in CHANNEL_TABS:
                if base.lower().endswith(tab):
                    base = base[:-len(tab)]
            return '%s/search?query=%s' % (base, wanted)
        if channel.startswith('@'):
            return 'https://www.youtube.com/%s/search?query=%s' % (channel,
                                                                   wanted)
        if channel.startswith('UC') and len(channel) == 24:
            return ('https://www.youtube.com/channel/%s/search?query=%s'
                    % (channel, wanted))
        return 'https://www.youtube.com/@%s/search?query=%s' % (channel,
                                                                wanted)

    def search(self, title, channel=None):
        """The id of the video that best matches `title`, or None."""
        if not title:
            return None
        if channel:
            command = [self.ytdlp, '--get-id', '--playlist-items', '1',
                       self.channel_search_url(channel, title)]
        else:
            command = [self.ytdlp, '--get-id', 'ytsearch1:%s' % title]

        ok, out = self.run(command, self.timeout)
        if not ok or not out.strip():
            return None
        # A channel search answers with a list; the first line is the match.
        return out.strip().splitlines()[0].strip() or None

    def metadata(self, video_id):
        """Everything YouTube will say about one video, or None."""
        if not video_id:
            return None
        ok, out = self.run(
            [self.ytdlp, '--dump-json', '--no-download',
             'https://www.youtube.com/watch?v=%s' % video_id], self.timeout)
        if not ok or not out.strip():
            return None
        try:
            found = json.loads(out)
        except ValueError:
            return None
        return found if isinstance(found, dict) else None

    # -- the file itself ---------------------------------------------------

    def stream_info(self, video_path):
        """What the video actually is, or None when ffprobe cannot say.

        None is an ordinary answer: the NFO has a default shape for it, and
        Kodi fills in the truth on its next scan.
        """
        ok, out = self.run([self.ffprobe, '-v', 'quiet', '-print_format',
                            'json', '-show_format', '-show_streams',
                            video_path], self.timeout)
        if not ok or not out.strip():
            return None
        try:
            data = json.loads(out)
        except ValueError:
            return None

        streams = data.get('streams') or []
        video = next((s for s in streams if s.get('codec_type') == 'video'),
                     None)
        audio = next((s for s in streams if s.get('codec_type') == 'audio'),
                     None)
        if not video:
            return None

        try:
            width = int(video.get('width', 1920))
            height = int(video.get('height', 1080))
        except (TypeError, ValueError):
            width, height = 1920, 1080
        try:
            duration = int(float(data.get('format', {}).get('duration', 0)))
        except (TypeError, ValueError):
            duration = 0

        return {
            'video': {
                'codec': video.get('codec_name', 'h264'),
                'width': width,
                'height': height,
                'aspect': round(width / float(height), 3) if height else 1.778,
                'duration_seconds': duration,
                'scantype': 'progressive',
            },
            'audio': {
                'codec': (audio or {}).get('codec_name', 'aac'),
                'channels': int((audio or {}).get('channels', 2) or 2),
            },
        }
