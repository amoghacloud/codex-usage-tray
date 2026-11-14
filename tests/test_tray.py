import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('tray', Path(__file__).resolve().parents[1] / 'tray.py')
tray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tray)

class UsageTests(unittest.TestCase):
    def test_remaining_and_expired_reset(self):
        self.assertIn('30% left', tray.window_text({'usedPercent': 70, 'windowDurationMins': 300, 'resetsAt': 2000}, 1000))
        text = tray.window_text({'usedPercent': 100, 'windowDurationMins': 10080, 'resetsAt': 500}, 1000)
        self.assertIn('0% left', text)
        self.assertIn('refresh needed', text)

    def test_account_change_is_not_saved_to_wrong_identity(self):
        a = {'account': {'type': 'chatgpt', 'email': 'one@example.com'}, 'userId': 'one'}
        b = {'account': {'type': 'chatgpt', 'email': 'two@example.com'}, 'userId': 'two'}
        rpc = mock.Mock()
        rpc.call.side_effect = [a, {'rateLimits': {}}, b]
        with mock.patch.object(tray, 'Rpc', return_value=rpc):
            with self.assertRaisesRegex(RuntimeError, 'Account changed'):
                tray.snapshot()
        rpc.close.assert_called_once()

    def test_signed_out_connection_closes(self):
        rpc = mock.Mock()
        rpc.call.return_value = {'account': None}
        with mock.patch.object(tray, 'Rpc', return_value=rpc):
            with self.assertRaisesRegex(RuntimeError, 'Sign into'):
                tray.snapshot()
        rpc.close.assert_called_once()

    def test_demo_never_loads_history_or_calls_codex(self):
        with mock.patch.object(tray, 'load', side_effect=AssertionError('real history read')), mock.patch.object(tray, 'Rpc', side_effect=AssertionError('Codex started')), mock.patch.object(tray, 'save', side_effect=AssertionError('history changed')):
            data = tray.demo_data(100000)
            app = tray.App.__new__(tray.App)
            app.demo = True
            app.render = mock.Mock()
            self.assertTrue(app.refresh())
        self.assertEqual(len(data['accounts']), 4)
        self.assertTrue(all(a['email'].endswith('@example.com') for a in data['accounts'].values()))

    def test_history_is_private_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(tray, 'STATE', Path(directory)):
            data = tray.demo_data(100000)
            tray.save(data)
            self.assertEqual(tray.load(), data)
            self.assertEqual((Path(directory) / 'accounts.json').stat().st_mode & 0o777, 0o600)

if __name__ == '__main__':
    unittest.main()
