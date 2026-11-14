"""macOS and Windows tray interface."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from PySide6.QtCore import QObject, QLockFile, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import tray


class DesktopTray(QObject):
    result = Signal(object, object)

    def __init__(self, app, demo):
        super().__init__()
        self.app = app
        self.demo = demo
        self.data = tray.demo_data() if demo else tray.load()
        self.active = 'demo-0' if demo else None
        self.busy = False
        self.error = None
        self.result.connect(self.finish)
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.render)
        self.icon = QSystemTrayIcon(QIcon(str(tray.ROOT / 'icon.svg')), self)
        self.icon.setContextMenu(self.menu)
        self.render()
        self.icon.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        if not demo:
            self.timer.start(60_000)
            self.refresh()

    def render(self):
        self.menu.clear()
        now = time.time()
        accounts = self.data['accounts']
        title = f'Codex Usage · {len(accounts)} accounts saved'
        if self.demo:
            title += ' · demo'
        self.menu.addAction(title)
        self.menu.addSeparator()
        for key, account in sorted(accounts.items(), key=lambda pair: (
                pair[0] != self.active,
                not tray.likely_available_after_reset(pair[1], now),
                pair[1]['email'])):
            title = account['email']
            if account.get('workspace'):
                title += f" · {account['workspace']}"
            if key == self.active:
                title += ' · current'
            details = self.menu.addMenu(title)
            self.menu.addAction(tray.account_summary(account, now))
            age = tray.duration(now - account['checked_at'])
            details.addAction(f"Checked {age} ago · {account.get('plan') or 'Plan unknown'}")
            details.addAction(tray.account_status(account, now))
            for name, limit in account.get('limits', {}).items():
                if len(account['limits']) > 1:
                    details.addAction(limit.get('limitName') or name)
                for field in ('primary', 'secondary'):
                    if limit.get(field):
                        details.addAction(tray.window_text(limit[field], now))
        current = accounts.get(self.active)
        tooltip = tray.account_summary(current, now) if current else 'No current reading'
        self.icon.setToolTip(f'Codex Usage · {tooltip}')
        self.menu.addSeparator()
        if self.error:
            self.menu.addAction(self.error)
        if not self.demo:
            refresh = self.menu.addAction('Refreshing…' if self.busy else 'Refresh now', self.refresh)
            refresh.setEnabled(not self.busy)
            self.menu.addAction('Forget saved accounts…', self.forget)
        self.menu.addAction('Quit', self.app.quit)

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        if not self.menu.isVisible():
            self.render()

        def worker():
            try:
                self.result.emit(tray.snapshot(), None)
            except RuntimeError as error:
                self.result.emit(None, str(error))
            except Exception:
                self.result.emit(None, 'Unable to connect to Codex · try Refresh again')

        threading.Thread(target=worker, daemon=True).start()

    def finish(self, result, error):
        self.busy = False
        self.error = error
        self.active = None
        if result:
            self.active, account = result
            self.data['accounts'][self.active] = account
            try:
                tray.save(self.data)
            except OSError:
                self.error = 'Could not save account history locally'
        if not self.menu.isVisible():
            self.render()

    def forget(self):
        answer = QMessageBox.question(None, 'Codex Usage Tray', 'Forget all saved usage readings?')
        if answer == QMessageBox.StandardButton.Yes:
            data = {'accounts': {}}
            try:
                tray.save(data)
            except OSError:
                QMessageBox.warning(None, 'Codex Usage Tray', 'Could not clear account history.')
                return
            self.data = data
            self.active = None
            self.render()


def run(demo):
    if sys.platform == 'darwin':
        os.environ.setdefault('QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM', '1')
    app = QApplication(['Codex Usage Tray'])
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, 'Codex Usage Tray', 'No system tray is available in this desktop session.')
        return
    state = Path(tempfile.gettempdir()) if demo else tray.STATE
    state.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(state / ('codex-usage-tray-demo.lock' if demo else 'tray.lock')))
    if not lock.tryLock(0):
        return
    desktop = DesktopTray(app, demo)
    try:
        app.exec()
    finally:
        desktop.icon.hide()
        lock.unlock()


if __name__ == '__main__':
    tray.main()
