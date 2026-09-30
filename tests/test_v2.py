import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
import portable_app as app
from connect_ui import ConnectUI


class ServiceTests(unittest.TestCase):
    def test_all_service_payloads(self):
        for key, suffix in [('campus', ''), ('telecom', '@telecom'), ('mobile', '@cmcc'), ('unicom', '@unicom')]:
            with self.subTest(service=key), \
                 patch.object(app, 'request', side_effect=[(200, 'eportal', {}), (302, '')]) as req, \
                 patch.object(app, 'online', return_value=True), patch.object(app.time, 'sleep'):
                self.assertEqual(app.login('10.0.0.1', {'username': '20260001', 'password': 'a&+中', 'service': key}), 'online')
                form = parse_qs(req.call_args.kwargs['body'].decode())
                self.assertEqual(form['DDDDD'], [',0,20260001' + suffix])
                self.assertEqual(form['upass'], ['a&+中'])

    def test_changing_service_removes_old_suffix(self):
        self.assertEqual(app.account_for_service('123@telecom', 'campus'), '123')
        self.assertEqual(app.account_for_service('123@unicom', 'mobile'), '123@cmcc')

    def test_unknown_service_and_malformed_user(self):
        for username, service in [('123', 'other'), ('', 'campus'), ('0,123', 'telecom'), ('123@unknown', 'campus')]:
            with self.assertRaises(ValueError):
                app.account_for_service(username, service)

    def test_no_reconnect_exits_when_connected(self):
        cfg = json.dumps(dict(username='test', password='dummy', reconnect=False)).encode()
        with patch.object(app, 'CONFIG') as config, patch.object(app, 'protect', return_value=cfg), \
             patch.object(app, 'wired_ip', return_value='10.0.0.1'), \
             patch.object(app, 'online', return_value=True), patch.object(app, 'notify_success'), \
             patch.object(app, 'set_state') as state, patch.object(app, 'login') as login, \
             patch.object(app, 'RotatingFileHandler', return_value=app.logging.NullHandler()):
            config.exists.return_value = True
            config.stat.return_value.st_mtime_ns = 1
            app.worker_loop()
            state.assert_called_with('completed')
            login.assert_not_called()

    def test_no_autostart_removes_shortcut_only(self):
        with patch.object(app, 'FROZEN', False), patch.object(app, 'STARTUP') as shortcut, \
             patch.object(app, 'powershell') as ps:
            command = app.install_startup(False)
            shortcut.unlink.assert_called_once_with(missing_ok=True)
            ps.assert_not_called()
            self.assertEqual(command[-1], '--worker')

    def test_encrypted_saved_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cfg = dict(username='fictional', password='fake', service='campus', autostart=False, reconnect=False)
            with patch.object(app, 'ROOT', folder), patch.object(app, 'CONFIG', folder / 'credentials.dpapi'), \
                 patch.object(app, 'STATE', folder / 'status.json'), \
                 patch.object(app, 'install_startup', return_value=['dummy', '--worker']) as install, \
                 patch.object(app, 'stop_worker'), patch.object(app.subprocess, 'Popen'):
                app.save_configuration(cfg)
                saved = app.CONFIG.read_bytes()
                self.assertNotIn(b'fictional', saved)
                self.assertEqual(json.loads(app.protect(saved, decrypt=True)), cfg)
                install.assert_called_once_with(False)


class InterfaceTests(unittest.TestCase):
    def test_selection_and_options_reach_saved_config(self):
        ui = ConnectUI(app, preview=True)
        ui.root.withdraw()
        try:
            for key in app.SERVICES:
                ui.select_service(key)
                self.assertEqual(ui.service.get(), key)
                self.assertEqual(ui.cards[key][1].cget('text'), '●')
            ui.select_service('campus')
            ui.username.insert(0, '20260001')
            ui.password.insert(0, 'fake-secret')
            ui.autostart.set(False)
            ui.reconnect.set(False)
            ui.preview = False
            def immediate(operation, done):
                operation()
                done()
            with patch.object(ui, 'run_async', side_effect=immediate), patch.object(app, 'save_configuration') as save:
                ui.save()
                cfg = save.call_args.args[0]
                self.assertEqual(cfg['service'], 'campus')
                self.assertEqual(cfg['username'], '20260001')
                self.assertFalse(cfg['autostart'])
                self.assertFalse(cfg['reconnect'])
                self.assertEqual(ui.password.get(), '')
        finally:
            ui.root.destroy()


if __name__ == '__main__':
    unittest.main()

