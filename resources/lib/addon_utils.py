# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The small things every other module needs from Kodi: where the add-on is,
what its settings say, and how to say something to the user.

Kept in one place so the rest of the add-on imports Kodi through here rather
than reaching for xbmcaddon itself, which is also what lets the tests answer
for Kodi without a single mock inside the modules that do the work.
"""

import os

import xbmc
import xbmcaddon
import xbmcgui

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = ADDON.getAddonInfo('path')
ADDON_VERSION = ADDON.getAddonInfo('version')

ICON = os.path.join(ADDON_PATH, 'icon.png')


def profile_dir():
    """The add-on's own folder under the user's profile, created if need be.

    Where the show list lives. The script kept summaries.json beside itself,
    which works for a script you run from one directory and not for an add-on,
    whose folder is replaced wholesale by every update.
    """
    path = xbmc.translatePath(ADDON.getAddonInfo('profile'))
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            pass
    return path


def get_setting(name, fallback=''):
    """A setting as text, or `fallback` when it has never been set."""
    try:
        value = ADDON.getSetting(name)
    except Exception:
        return fallback
    if value is None or value == '':
        return fallback
    return value


def get_bool(name, fallback=False):
    value = get_setting(name, '')
    if value == '':
        return fallback
    return value.lower() == 'true'


def get_int(name, fallback=0):
    try:
        return int(float(get_setting(name, '')))
    except (TypeError, ValueError):
        return fallback


def set_setting(name, value):
    try:
        ADDON.setSetting(name, value)
        return True
    except Exception:
        return False


def log(message, level=xbmc.LOGNOTICE):
    """A line in Kodi's log, tagged so it can be found among everyone else's.

    The script printed 91 times, mostly to say what it was doing to which
    file. Those become log lines rather than notifications: a harvest of
    twenty files should not be twenty toasts.
    """
    try:
        xbmc.log('[%s] %s' % (ADDON_ID, message), level)
    except Exception:
        pass


def notify(message, heading=None, millis=4000):
    """A toast, unless the user has turned them off."""
    if not get_bool('show_notifications', True):
        return
    force_notify(message, heading, millis)


def force_notify(message, heading=None, millis=4000):
    """A toast that ignores that setting, for something that went wrong."""
    try:
        xbmcgui.Dialog().notification(heading or ADDON_NAME, message,
                                      ICON, millis)
    except Exception:
        log('notification failed: %s' % message, xbmc.LOGWARNING)
