#!/usr/bin/python3
"""Install Codex Usage Tray for the current user; no sudo required."""
import argparse
import ctypes.util
from pathlib import Path
import shutil
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--autostart', action='store_true', help='Also start automatically at login')
    args = parser.parse_args()
    try:
        import gi
        gi.require_version('Gtk', '3.0')
    except (ImportError, ValueError):
        sys.exit('Missing GTK Python support. See the README dependency command.')
    if not (ctypes.util.find_library('ayatana-appindicator3') or ctypes.util.find_library('appindicator3')):
        sys.exit('Missing AppIndicator library. See the README dependency command.')
    if not (shutil.which('codex') or (Path.home() / '.local/bin/codex').is_file()):
        sys.exit('Codex CLI not found. Install the official CLI and sign in first; see README.')
    source = Path(__file__).resolve().parent
    target = Path.home() / '.local/share/codex-usage-tray'
    target.mkdir(parents=True, exist_ok=True)
    for name in ['tray.py', 'icon.svg', 'README.md', 'LICENSE', 'uninstall.py']:
        if source != target:
            shutil.copy2(source / name, target / name)
    exec_path = str(target / 'tray.py').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    desktop = f'''[Desktop Entry]
Type=Application
Name=Codex Usage Tray
Comment=Remember usage across your Codex accounts
Exec=/usr/bin/python3 "{exec_path}"
Icon={target / 'icon.svg'}
Terminal=false
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
'''
    folders = [Path.home() / '.local/share/applications']
    if args.autostart:
        folders.append(Path.home() / '.config/autostart')
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'codex-usage-tray.desktop').write_text(desktop)
    print('Installed. Launch Codex Usage Tray from your applications menu.')
    if args.autostart:
        print('Automatic startup at login enabled.')

if __name__ == '__main__':
    main()
