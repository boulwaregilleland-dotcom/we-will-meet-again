import unittest
from unittest.mock import patch
import portable_app as app
from native_adapters import snapshot

CFG=dict(transport='wireless',service='telecom',profiles={
    'wireless:telecom':dict(username='wireless-only',password='wp'),
    'wired:campus':dict(username='free-only',password='fp'),
    'wired:telecom':dict(username='paid-only',password='pp')})

class WiredTests(unittest.TestCase):
    def setUp(self):app._rejected_profiles.clear()
    def tearDown(self):app._rejected_profiles.clear()

    def test_legacy_two_profiles_no_longer_ambiguous(self):
        with patch.object(app,'wireless_ip',return_value=None),patch.object(app,'wired_ip',return_value='10.0.0.1'):
            ip,cfg,error=app.connection_for_config(CFG)
            self.assertEqual(cfg['service'],'campus')
            self.assertIsNone(error)

    def test_free_then_saved_operator_separate_credentials(self):
        with patch.object(app,'login',side_effect=['authentication_unverified','online']) as login:
            self.assertEqual(app.login_connection('10.0.0.1',dict(CFG,transport='wired')),'online')
            self.assertEqual([c.args[1]['username'] for c in login.call_args_list],['free-only','paid-only'])
            self.assertEqual([c.args[1]['password'] for c in login.call_args_list],['fp','pp'])

    def test_free_success_stops_fallback(self):
        with patch.object(app,'login',return_value='online') as login:
            app.login_connection('10.0.0.1',dict(CFG,transport='wired'))
            self.assertEqual(login.call_count,1)

    def test_rejected_free_not_repeated(self):
        with patch.object(app,'login',side_effect=['credentials_rejected','authentication_unverified','online']) as login:
            cfg=dict(CFG,transport='wired')
            app.login_connection('10.0.0.1',cfg)
            app.login_connection('10.0.0.1',cfg)
            self.assertEqual([c.args[1]['service'] for c in login.call_args_list],['campus','telecom','telecom'])

    def test_portal_unavailable_does_not_cycle_accounts(self):
        with patch.object(app,'login',return_value='portal_unavailable') as login:
            app.login_connection('10.0.0.1',dict(CFG,transport='wired'))
            self.assertEqual(login.call_count,1)

    def test_native_snapshot_readonly(self):
        rows=snapshot()
        self.assertIsInstance(rows,list)
        self.assertTrue(all(isinstance(r['kind'],int) and isinstance(r['ips'],list) for r in rows))

    def test_fast_native_wifi_uses_matching_guid(self):
        row=dict(guid='12345678-1234-1234-1234-123456789abc',kind=71,ips=['10.0.0.1'])
        with patch.object(app,'fast_adapters',return_value=[row]),patch.object(app.subprocess,'run') as run:
            run.return_value.stdout=b'GUID : 12345678-1234-1234-1234-123456789abc\nSSID : ECJTU-Stu\n'
            self.assertEqual(app.wireless_ip(),'10.0.0.1')

if __name__=='__main__':unittest.main()
