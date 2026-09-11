# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

Telling Kodi that something changed.

The script did this over HTTP, to a Kodi somewhere else, which meant a host,
a port, a username and a password in the arguments. Running inside Kodi there
is no network and no credentials: the same JSON-RPC goes straight into the
process it is already in.
"""

import json

import xbmc

import addon_utils as utils


def call(method, params=None):
    """One JSON-RPC call into this Kodi. The parsed answer, or None."""
    request = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        request['params'] = params
    try:
        answer = xbmc.executeJSONRPC(json.dumps(request))
        return json.loads(answer)
    except (ValueError, TypeError) as exc:
        utils.log('JSON-RPC %s failed: %s' % (method, exc))
        return None


def scan(directory=None):
    """Ask Kodi to scan the video library, or one folder of it.

    A folder is worth naming when there is one: a full scan of a library this
    add-on has been filling for a year is minutes of disk, and what changed is
    one show.
    """
    params = {}
    if directory:
        # Kodi wants a trailing separator on a directory, and answers a path
        # without one by scanning nothing at all.
        if not directory.endswith(('/', '\\')):
            directory += '\\' if '\\' in directory else '/'
        params['directory'] = directory
    return call('VideoLibrary.Scan', params or None)


def refresh_folders(paths):
    """Scan each folder in `paths`, once each, in a settled order."""
    done = set()
    for path in paths or []:
        if path in done:
            continue
        done.add(path)
        scan(path)
    return len(done)
