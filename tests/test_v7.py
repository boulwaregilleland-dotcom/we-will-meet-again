import json
import unittest
from unittest.mock import patch
import portable_app as app
from connect_ui import ConnectUI

GUID = '12345678-1234-1234-1234-123456789abc'


class WirelessTests(unittest.TestCase):
    def test_localized_interfaces_and_bssid(self):
        text = f'名称 : WLAN\n GUID : {GUID}\n 状态 : 已连接\n SSID : ECJTU-Stu\n BSSID : aa:bb:cc:dd:ee:ff\n'
        self.assertEqual(app.wifi_connections(text), [(GUID, 'ECJTU-Stu')])
        with patch.object(app, 'powershell', side_effect=[text, '169.254.1.1\n10.3.4.5']) as ps:
            self.assertEqual(app.wireless_ip_legacy(), '10.3.4.5')
            self.assertIn(GUID, ps.call_args.args[0])

    def test_other_wifi_never_used(self):
        for ssid in ['Home', 'ECJTU-Stu-guest', 'ECJTU-Stu evil']:
            with patch.object(app,'powershell',return_value=f'GUID : {GUID}\nSSID : {ssid}\n') as ps:
                self.assertIsNone(app.wireless_ip_legacy())
                self.assertEqual(ps.call_count, 1)

    def test_disconnected_wifi(self):
        with patch.object(app,'powershell',return_value=f'GUID : {GUID}\n状态 : 已断开连接\n'):
            self.assertIsNone(app.wireless_ip_legacy())

    def test_real_powershell_adapter_guid_format(self):
        # Run generated selection against realistic Windows objects, not mocked text.
        real_ps = app.powershell
        def probe(code):
            if 'netsh.exe' in code:
                return f'GUID : {GUID}\nSSID : ECJTU-Stu\n'
            fixtures = "function Get-NetAdapter { [pscustomobject]@{InterfaceGuid='{12345678-1234-1234-1234-123456789ABC}';Status='Up';ifIndex=7} };"
            fixtures += "function Get-NetIPAddress { param($InterfaceIndex,$AddressFamily,$ErrorAction) [pscustomobject]@{IPAddress='10.3.4.5';AddressState='Preferred'} };"
            return real_ps(fixtures + code)
        with patch.object(app, 'powershell', side_effect=probe):
            self.assertEqual(app.wireless_ip_legacy(), '10.3.4.5')

    def test_worker_wireless_never_uses_ethernet(self):
        cfg = json.dumps(dict(username='fiction',password='fake',transport='wireless',reconnect=False)).encode()
        with patch.object(app,'CONFIG') as config, patch.object(app,'protect',return_value=cfg), \
             patch.object(app,'wireless_ip',return_value='10.3.4.5') as wifi, \
             patch.object(app,'wired_ip') as wired, patch.object(app,'online',return_value=True), patch.object(app,'notify_success'), \
             patch.object(app,'set_state') as state, patch.object(app,'login') as login, \
             patch.object(app,'RotatingFileHandler',return_value=app.logging.NullHandler()):
            config.exists.return_value=True
            config.stat.return_value.st_mtime_ns=1
            app.worker_loop()
            wifi.assert_called_once()
            wired.assert_not_called()
            login.assert_not_called()
            state.assert_called_with('completed')

    def test_legacy_migration_only_original_module(self):
        self.assertEqual(app.saved_profiles(dict(username='u',password='p',service='mobile')),
                         {'wired:mobile':dict(username='u',password='p')})


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.ui=ConnectUI(app,preview=True)
        self.ui.root.withdraw()
        self.ui.preview=False
        self.saved=[]
        self.saver=patch.object(app,'save_configuration',side_effect=lambda cfg:self.saved.append(cfg))
        self.saver.start()
        self.ui.run_async=lambda operation,done:(operation(),done())

    def tearDown(self):
        self.saver.stop()
        self.ui.root.destroy()

    def enter(self,user,password):
        self.ui.username.delete(0,'end')
        self.ui.username.insert(0,user)
        self.ui.password.delete(0,'end')
        self.ui.password.insert(0,password)

    def test_separate_passwords_and_blank_reuse(self):
        ui=self.ui
        self.enter('same','wired-password')
        ui.save()
        ui.transport.set('wireless')
        ui.select_service('telecom')
        self.assertEqual(ui.username.get(),'')
        self.assertEqual(ui.password.get(),'')
        self.enter('same','wifi-password')
        ui.save()
        ui.transport.set('wired')
        ui.select_service('telecom')
        self.assertEqual(ui.username.get(),'same')
        ui.save()
        cfg=self.saved[-1]
        self.assertEqual(cfg['password'],'wired-password')
        self.assertEqual(cfg['profiles']['wireless:telecom']['password'],'wifi-password')
        self.assertEqual(cfg['profiles']['wired:telecom']['password'],'wired-password')
        encrypted=app.protect(json.dumps(cfg).encode())
        self.assertNotIn(b'wifi-password',encrypted)
        self.assertEqual(json.loads(app.protect(encrypted,decrypt=True)),cfg)

    def test_switching_service_does_not_reuse_password(self):
        ui=self.ui
        self.enter('u','p')
        ui.save()
        ui.select_service('campus')
        self.enter('u','')
        with patch('connect_ui.messagebox.showwarning') as warning:
            ui.save()
            warning.assert_called_once()
        self.assertEqual(len(self.saved),1)

    def test_unsaved_draft_survives_switch(self):
        ui=self.ui
        self.enter('draft','draft-secret')
        ui.select_service('campus')
        self.assertEqual(ui.password.get(),'')
        ui.select_service('telecom')
        self.assertEqual(ui.password.get(),'draft-secret')

    def test_saved_profiles_restore_after_reopen(self):
        self.enter('u','p')
        self.ui.save()
        cfg=self.saved[-1]
        with patch.object(app,'CONFIG') as config, patch.object(app,'protect',return_value=json.dumps(cfg).encode()):
            config.exists.return_value=True
            other=ConnectUI(app)
        try:
            self.assertEqual(other.username.get(),'u')
            self.assertEqual(other.password.get(),'')
            self.assertEqual(other.profiles['wired:telecom']['password'],'p')
        finally:
            other.root.destroy()


if __name__ == '__main__':
    unittest.main()

