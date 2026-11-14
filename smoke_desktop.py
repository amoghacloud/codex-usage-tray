"""Exercise the desktop menu on CI without a real tray or a Codex login."""
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from desktop import DesktopTray

app = QApplication([])
with patch.object(QSystemTrayIcon, 'show'):
    demo = DesktopTray(app, True)
labels = [action.text() for action in demo.menu.actions()]
assert sum('@example.com' in label for label in labels) == 4
assert 'Quit' in labels
assert 'Refresh now' not in labels
assert '5h 65% left · Week 82% left' in labels
print('Desktop demo menu passed')
