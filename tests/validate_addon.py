# -*- coding: utf-8 -*-
"""
Paragon Harvester - manifest and settings validation.

Kodi fails quietly on all of this: a mistyped setting id reads back as an
empty string, a library file named in addon.xml that is not there stops the
add-on loading with a line in the log nobody is watching, and a malformed
addon.xml means the add-on never appears at all. None of it raises anywhere a
test can see, so it is checked here.

    python3 tests/validate_addon.py
"""

from __future__ import print_function

import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ADDON_ID = 'script.paragon.harvester'

# Settings that exist as a button in the settings screen; nothing reads them.
ACTION_ONLY = {'run_now'}

SETTING_CALL = re.compile(
    r"""(?:get_setting|get_bool|get_int|set_setting)\(\s*['"]([\w.]+)['"]""")

problems = []
notes = []


def fail(message):
    problems.append(message)


def sources():
    """Every Python file the add-on ships."""
    found = [os.path.join(ROOT, name) for name in ('default.py', 'service.py')]
    lib = os.path.join(ROOT, 'resources', 'lib')
    for name in sorted(os.listdir(lib)):
        if name.endswith('.py'):
            found.append(os.path.join(lib, name))
    return [path for path in found if os.path.isfile(path)]


def read(path):
    handle = open(path, 'r')
    try:
        return handle.read()
    finally:
        handle.close()


def check_addon_xml():
    path = os.path.join(ROOT, 'addon.xml')
    if not os.path.isfile(path):
        fail('addon.xml is missing')
        return
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        fail('addon.xml is not valid XML: %s' % exc)
        return

    if root.get('id') != ADDON_ID:
        fail('addon.xml id is %r, expected %r' % (root.get('id'), ADDON_ID))
    for attribute in ('name', 'version', 'provider-name'):
        if not root.get(attribute):
            fail('addon.xml is missing the %s attribute' % attribute)

    points = {}
    for extension in root.findall('extension'):
        points[extension.get('point')] = extension
    for point in ('xbmc.python.script', 'xbmc.service'):
        if point not in points:
            fail('addon.xml declares no %s' % point)
            continue
        library = points[point].get('library')
        if not library:
            fail('%s names no library' % point)
        elif not os.path.isfile(os.path.join(ROOT, library)):
            fail('%s names %s, which is not there' % (point, library))

    metadata = points.get('xbmc.addon.metadata')
    if metadata is not None:
        for asset in metadata.findall('assets/*'):
            if asset.text and not os.path.isfile(
                    os.path.join(ROOT, asset.text)):
                fail('addon.xml promises %s, which is not there' % asset.text)


def check_settings():
    """Every setting the code reads must be declared, and the other way."""
    path = os.path.join(ROOT, 'resources', 'settings.xml')
    if not os.path.isfile(path):
        fail('resources/settings.xml is missing')
        return set()
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        fail('settings.xml is not valid XML: %s' % exc)
        return set()

    declared = set()
    for setting in root.iter('setting'):
        if setting.get('id'):
            declared.add(setting.get('id'))

    used = set()
    for source in sources():
        used.update(SETTING_CALL.findall(read(source)))

    for name in sorted(used - declared):
        fail('the code reads a setting called %s, which settings.xml does not '
             'declare' % name)
    for name in sorted(declared - used - ACTION_ONLY):
        notes.append('%s is declared but nothing reads it' % name)
    return declared


def check_actions():
    """Actions the README documents must be ones default.py handles."""
    readme = os.path.join(ROOT, 'README.md')
    if not os.path.isfile(readme):
        notes.append('no README.md')
        return
    documented = set(re.findall(r'action=(\w+)', read(readme)))
    handled = set(re.findall(r"action == '(\w+)'",
                             read(os.path.join(ROOT, 'default.py'))))
    for action in sorted(documented - handled):
        fail('README documents action=%s, which default.py does not handle'
             % action)


def main():
    check_addon_xml()
    declared = check_settings()
    check_actions()

    for note in notes:
        print('note    %s' % note)
    for problem in problems:
        print('FAIL    %s' % problem)
    if problems:
        print('\n%d problem(s)' % len(problems))
        return 1
    print('\naddon.xml and settings.xml validate; %d setting(s) declared'
          % len(declared))
    return 0


if __name__ == '__main__':
    sys.exit(main())
