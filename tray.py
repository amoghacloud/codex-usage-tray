#!/usr/bin/python3
"""Local-only Codex account usage indicator. No credentials are read or stored."""
import argparse
import ctypes
import ctypes.util
import fcntl
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import threading
import time

VERSION = '0.1.0'
ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'codex-usage-tray'


class Rpc:
    def __init__(self):
        binary = shutil.which('codex') or str(Path.home() / '.local/bin/codex')
        self.p = subprocess.Popen([binary, 'app-server', '--listen', 'stdio://'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.p.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.serial = 0
        try:
            self.call('initialize', {'clientInfo': {'name': 'codex_usage_tray', 'title': 'Codex Usage Tray', 'version': VERSION}, 'capabilities': None})
            self.send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def send(self, obj):
        self.p.stdin.write((json.dumps(obj) + '\n').encode())
        self.p.stdin.flush()

    def call(self, method, params):
        self.serial += 1
        ident = self.serial
        self.send({'id': ident, 'method': method, 'params': params})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if b'\n' not in self.buffer:
                if not self.selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('Codex connection closed')
                self.buffer += chunk
                continue
            line, self.buffer = self.buffer.split(b'\n', 1)
            obj = json.loads(line)
            if obj.get('id') != ident:
                continue
            if 'error' in obj:
                # Do not persist backend error bodies; they may contain account data.
                raise RuntimeError('Codex could not return usage; try Refresh again')
            return obj['result']
        raise RuntimeError('Codex usage check timed out')

    def close(self):
        self.selector.close()
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()


def snapshot():
    rpc = Rpc()
    try:
        before = rpc.call('account/read', {'refreshToken': False})
        account = before.get('account') or {}
        if account.get('type') != 'chatgpt':
            raise RuntimeError('Sign into a ChatGPT account in Codex first')
        usage = rpc.call('account/rateLimits/read', {'excludeResetCreditDetails': True})
        after = rpc.call('account/read', {'refreshToken': False})
        if before != after:
            raise RuntimeError('Account changed during refresh; checking again shortly')
        email = account.get('email')
        if not email:
            raise RuntimeError('Codex did not provide an account email')
        identity = json.dumps([email, account.get('workspaceName'), before.get('userId')])
        return identity, {'email': email, 'workspace': account.get('workspaceName'),
                          'plan': account.get('planType'), 'checked_at': time.time(),
                          'allowed': usage.get('ordinaryUsageAllowed'),
                          'limits': usage.get('rateLimitsByLimitId') or {'codex': usage.get('rateLimits') or {}}}
    finally:
        rpc.close()


def load():
    try:
        data = json.loads((STATE / 'accounts.json').read_text())
        if isinstance(data, dict) and isinstance(data.get('accounts'), dict):
            return data
    except (OSError, ValueError):
        pass
    return {'accounts': {}}


def save(data):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE / 'accounts.tmp'
    fd = os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
    tmp.replace(STATE / 'accounts.json')


def duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return 'less than 1m'
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f'{minutes}m'
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f'{hours}h {minutes}m'
    days, hours = divmod(hours, 24)
    return f'{days}d {hours}h'


def window_text(window, now):
    if not window:
        return 'Usage unavailable'
    mins = window.get('windowDurationMins')
    label = 'Weekly' if mins == 10080 else '5-hour' if mins == 300 else (f'{mins // 60:g}-hour' if mins and mins % 60 == 0 else f'{mins}m' if mins else 'Usage')
    remaining = max(0, min(100, 100 - float(window.get('usedPercent', 100))))
    reset = window.get('resetsAt')
    suffix = ''
    if reset:
        suffix = f' · resets in {duration(reset - now)}' if reset > now else ' · reset time passed; refresh needed'
    return f'{label}: {remaining:g}% left{suffix}'


def demo_data(now=None):
    """Synthetic examples only: never load real accounts or contact Codex."""
    now = time.time() if now is None else now
    accounts = {}
    for index, (name, short, weekly, age) in enumerate([
            ('personal', 65, 82, 0), ('work', 0, 40, 1200),
            ('projects', 90, 71, 7200), ('weekend', 35, 18, 86400)]):
        accounts[f'demo-{index}'] = {
            'email': f'{name}@example.com', 'workspace': None, 'plan': 'plus',
            'checked_at': now - age, 'allowed': short > 0,
            'limits': {'codex': {
                'primary': {'usedPercent': 100-short, 'windowDurationMins': 300,
                            'resetsAt': now + (7200 if index != 1 else 2400)},
                'secondary': {'usedPercent': 100-weekly, 'windowDurationMins': 10080,
                              'resetsAt': now + 172800}}}}
    return {'accounts': accounts}


class App:
    def __init__(self, demo=False):
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
        self.Gtk, self.GLib = Gtk, GLib
        self.demo = demo
        self.data = demo_data() if demo else load()
        self.busy = False
        self.error = None
        self.active = 'demo-0' if demo else None
        self.lib = ctypes.CDLL(ctypes.util.find_library('ayatana-appindicator3') or 'libappindicator3.so.1')
        self.lib.app_indicator_new.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.app_indicator_new.restype = ctypes.c_void_p
        self.lib.app_indicator_set_menu.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.lib.app_indicator_set_status.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.app_indicator_set_label.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        self.indicator = self.lib.app_indicator_new(b'codex-usage-tray-demo' if demo else b'codex-usage-tray', str(ROOT / 'icon.svg').encode(), 0)
        self.lib.app_indicator_set_status(self.indicator, 1)
        self.render()
        GLib.timeout_add_seconds(60, self.refresh)
        GLib.timeout_add_seconds(30, self.tick)
        self.refresh()

    def item(self, menu, label, callback=None):
        item = self.Gtk.MenuItem.new_with_label(label)
        if callback:
            item.connect('activate', lambda *_: callback())
        else:
            item.set_sensitive(False)
        menu.append(item)
        return item

    def tick(self):
        self.render()
        return True

    def render(self):
        menu = self.Gtk.Menu()
        now = time.time()
        accounts = self.data['accounts']
        self.item(menu, f'Codex Usage · {len(accounts)} accounts saved')
        self.item(menu, 'DEMO · all accounts and readings are fictional' if self.demo else 'Updates the signed-in account every minute')
        menu.append(self.Gtk.SeparatorMenuItem())
        if not accounts:
            self.item(menu, 'Waiting for your first account…')
        for key, account in sorted(accounts.items(), key=lambda pair: (pair[0] != self.active, pair[1]['email'])):
            current = key == self.active
            age = max(0, now - account['checked_at'])
            title = account['email'] + (' · current' if current else ' · saved')
            if account.get('workspace'):
                title += ' · ' + account['workspace']
            self.item(menu, title)
            self.item(menu, f"  {account.get('plan') or 'Plan unknown'} · checked {duration(age)} ago")
            if account.get('allowed') is False:
                self.item(menu, '  Included usage blocked at last check')
            elif account.get('allowed') is True:
                self.item(menu, '  Included usage available at last check')
            for name, limit in account.get('limits', {}).items():
                if len(account['limits']) > 1:
                    self.item(menu, '  ' + (limit.get('limitName') or name))
                for field in ['primary', 'secondary']:
                    if limit.get(field):
                        self.item(menu, '  ' + window_text(limit[field], now))
                if not limit.get('primary') and not limit.get('secondary'):
                    self.item(menu, '  Usage percentages unavailable')
            menu.append(self.Gtk.SeparatorMenuItem())
        if self.error:
            self.item(menu, self.error)
        self.item(menu, 'Refreshing…' if self.busy else 'Refresh now', None if self.busy else self.refresh)
        if not self.demo:
            self.item(menu, 'Forget saved accounts…', self.forget)
        self.item(menu, 'Quit', self.Gtk.main_quit)
        menu.show_all()
        pointer = ctypes.pythonapi.PyCapsule_GetPointer
        pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
        pointer.restype = ctypes.c_void_p
        self.lib.app_indicator_set_menu(self.indicator, pointer(menu.__gpointer__, None))
        self.menu = menu
        current = accounts.get(self.active)
        label = 'Codex'
        if current:
            if current.get('allowed') is False:
                label = 'Codex · blocked'
            else:
                limit = current.get('limits', {}).get('codex') or next(iter(current.get('limits', {}).values()), {})
                window = limit.get('primary')
                if window:
                    label = f"Codex {max(0, min(100, 100 - float(window['usedPercent']))):g}%"
        if self.demo:
            label += ' · demo'
        self.lib.app_indicator_set_label(self.indicator, label.encode(), b'Codex 100%')

    def forget(self):
        dialog = self.Gtk.MessageDialog(message_type=self.Gtk.MessageType.QUESTION,
                    buttons=self.Gtk.ButtonsType.OK_CANCEL, text='Forget all saved usage readings?')
        dialog.format_secondary_text('The signed-in account will be added again on the next refresh.')
        if dialog.run() == self.Gtk.ResponseType.OK:
            self.data = {'accounts': {}}
            self.active = None
            save(self.data)
            self.render()
        dialog.destroy()

    def refresh(self):
        if self.demo:
            self.render()
            return True
        if self.busy:
            return True
        self.busy = True
        self.render()
        def worker():
            try:
                result, error = snapshot(), None
            except Exception as exc:
                result = None
                error = str(exc) if isinstance(exc, RuntimeError) else 'Unable to connect to Codex; try Refresh again'
            self.GLib.idle_add(self.finish, result, error)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def finish(self, result, error):
        self.busy = False
        self.error = error
        if result:
            key, account = result
            self.active = key
            self.data['accounts'][key] = account
            try:
                save(self.data)
            except OSError:
                self.error = 'Could not save account history locally'
        else:
            self.active = None
        self.render()
        return False

    def run(self):
        self.Gtk.main()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check connectivity without starting the tray')
    parser.add_argument('--demo', action='store_true', help='Show fictional accounts without accessing Codex or saved history')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args()
    if args.check:
        if args.demo:
            print(json.dumps(demo_data(), indent=2))
            return
        key, account = snapshot()
        print(json.dumps({'connected': True, 'plan': account['plan'], 'usage_windows': sum(bool(v.get(k)) for v in account['limits'].values() for k in ['primary', 'secondary'])}))
        return
    lock_dir = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'codex-usage-tray-{os.getuid()}' if args.demo else STATE
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (lock_dir / ('demo.lock' if args.demo else 'tray.lock')).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        App(demo=args.demo).run()


if __name__ == '__main__':
    main()
