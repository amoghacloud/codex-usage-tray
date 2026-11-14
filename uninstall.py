#!/usr/bin/python3
"""Remove this user's Codex Usage Tray installation. Choose Quit in the tray first."""
import argparse
import os
from pathlib import Path
import shutil

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--purge', action='store_true', help='Also delete saved account readings')
    args = parser.parse_args()
    for folder in ['.local/share/applications', '.config/autostart']:
        (Path.home() / folder / 'codex-usage-tray.desktop').unlink(missing_ok=True)
    shutil.rmtree(Path.home() / '.local/share/codex-usage-tray', ignore_errors=True)
    if args.purge:
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'codex-usage-tray'
        shutil.rmtree(state, ignore_errors=True)
    print('Uninstalled. Saved account readings ' + ('deleted.' if args.purge else 'preserved.'))

if __name__ == '__main__':
    main()
