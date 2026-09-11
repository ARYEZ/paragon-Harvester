# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The part that watches the download folder.

The script used watchdog, which is not something a Kodi 17.6 add-on can
import, so this looks on an interval instead. Polling is the poorer mechanism
in theory and the better one here: a download that has just finished is not
worth reacting to in the same second, and the settle time the harvester
applies would have made a file-system event wait anyway.

Everything it does, it does with nobody watching, so it never asks: a show it
has not seen is set up from the defaults and the user is told which ones
those were.
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'resources', 'lib'))

import xbmc                   # noqa: E402

import addon_utils as utils   # noqa: E402
import gui                    # noqa: E402

# Checked often enough that turning the service on takes effect without a
# restart, which is the interval a person notices rather than the interval the
# folder is read at.
TICK_SECONDS = 30


def due(waited, minutes):
    """True when a pass is due, given how long the loop has been waiting."""
    return waited >= max(1, minutes) * 60


def main():
    monitor = xbmc.Monitor()
    utils.log('service started')
    waited = 0

    while not monitor.abortRequested():
        if monitor.waitForAbort(TICK_SECONDS):
            break
        if not utils.get_bool('service_enabled', False):
            waited = 0
            continue

        waited += TICK_SECONDS
        if not due(waited, utils.get_int('poll_minutes', 15)):
            continue
        waited = 0

        if gui.folders_missing():
            # Said once a pass rather than once a tick: a folder that is not
            # set up is a settings problem, not an emergency.
            utils.log('nothing to watch yet: %s' % gui.folders_missing())
            continue
        try:
            gui.run_pass(None)
        except Exception as exc:              # noqa: BLE001
            utils.log('pass failed: %s' % exc, xbmc.LOGERROR)

    utils.log('service stopped')


if __name__ == '__main__':
    main()
