# -*- coding: utf-8 -*-
"""
Paragon Harvester
Creator: Aryez
Year: 2026
Part of: Paragon TV Project

What runs when the add-on is opened, or named by a keymap or a shortcut.

    RunScript(script.paragon.harvester)                 the menu
    RunScript(script.paragon.harvester,action=run)      a pass, now
    RunScript(script.paragon.harvester,action=quiet)    a pass, asking nothing
    RunScript(script.paragon.harvester,action=sanitise) clean up the NFOs
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'resources', 'lib'))

import addon_utils as utils   # noqa: E402 - the path has to go in first
import gui                    # noqa: E402


def parse_args(argv):
    """The key=value arguments Kodi passes, as a dict.

    Anything that is not key=value is ignored rather than fatal, because a
    keymap entry with a stray word in it should still open the menu.
    """
    args = {}
    for chunk in (argv or [])[1:]:
        if '=' in chunk:
            key, value = chunk.split('=', 1)
            args[key.strip()] = value.strip()
    return args


def main(argv):
    action = (parse_args(argv).get('action') or '').strip().lower()
    panel = gui.ControlPanel()

    if action == 'run':
        gui.run_pass(gui.Dialogs()
                     if utils.get_bool('ask_about_new_shows', True) else None)
    elif action == 'quiet':
        gui.run_pass(None)
    elif action == 'sanitise':
        panel.sanitise()
    elif action == 'settings':
        panel.settings()
    elif action:
        utils.force_notify('There is no action called "%s"' % action)
    else:
        panel.run()


if __name__ == '__main__':
    main(sys.argv)
