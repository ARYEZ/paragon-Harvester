# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

The one file allowed to know which Python it is running on.

Kodi 17.6 embeds Python 2.7 and the tests run on Python 3, so a handful of
standard-library names have to be looked up twice. Every one of those lives
here, behind a try/except on the import, and the rest of the add-on imports
from this module and never names a version-specific module itself. That is
also what lets check_py2.py fail the whole tree on a Python 3 import: this
file is its one exception.
"""

try:                       # Python 2.7, which is what Kodi 17.6 runs
    from urllib import quote
except ImportError:        # Python 3, which is what the tests run
    from urllib.parse import quote

try:
    string_types = (str, unicode)     # noqa: F821 - Python 2 only
except NameError:
    string_types = (str,)


def as_text(value, encoding='utf-8'):
    """`value` as a text string, whichever kind of string it arrived as.

    Python 2 hands back bytes from places Python 3 hands back text -- a
    subprocess's output, most of what json gives a non-ASCII name -- and a
    byte string that meets a unicode one decides for itself what encoding it
    was, in ASCII, and raises.
    """
    if value is None:
        return value
    if isinstance(value, bytes):
        return value.decode(encoding, 'replace')
    return value


def quoted(value):
    """`value` percent-encoded for a URL, from text or bytes."""
    if not isinstance(value, bytes):
        value = value.encode('utf-8')
    return quote(value)
