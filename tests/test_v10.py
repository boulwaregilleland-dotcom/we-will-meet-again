import json
import unittest
from unittest.mock import patch
import portable_app as app

CFG=dict(transport='wireless',service='telecom',reconnect=True,profiles={
    'wireless:telecom':dict(username='wifi-user',password='wifi-pass'),
    'wired:campus':dict(username='wired-user',password='wired-pass')})

class SwitchingTests(unittest.TestCase):
    def test_wifi_disappears_selects_wired_credentials(self):
        with patch.object(app,'wireless_ip',return_value=None),patch.object(app,'wired_ip',return_value='10.0.0.2'):
            ip,cfg,error=app.connection_for_config(CFG)
            self.assertEqual(cfg['username'],'wired-user')
            self.assertEqual(cfg['service'],'campus')
            self.assertIsNone(error)

    def test_no_password_cross_transport(self):
        cfg=dict(CFG,profiles={'wireless:telecom':CFG['profiles']['wireless:telecom']})
        with patch.object(app,'wireless_ip',return_value=None),patch.object(app,'wired_ip',return_value='10.0.0.2'):
            ip,_,error=app.connection_for_config(cfg)
            self.assertIsNone(ip)
            self.assertEqual(error,'profile_required')

    def test_switch_same_ip_reauthenticates_and_notifies_again(self):
        def effective(transport,service):
            return dict(CFG,transport=transport,service=service,**CFG['profiles'][transport+':'+service])
        states=[('10.0.0.2',effective('wireless','telecom'),None),('10.0.0.2',effective('wired','campus'),None)]
        with patch.object(app,'CONFIG') as config, patch.object(app,'protect',return_value=json.dumps(CFG).encode()), \
             patch.object(app,'connection_for_config',side_effect=states),patch.object(app,'online',return_value=False), \
             patch.object(app,'notify_success') as notice,patch.object(app.time,'sleep'), \
             patch.object(app,'RotatingFileHandler',return_value=app.logging.NullHandler()),patch.object(app,'set_state'):
            config.exists.return_value=True
            config.stat.return_value.st_mtime_ns=1
            calls=[]
            def login(ip,cfg):
                calls.append(cfg['username'])
                if len(calls)==2:config.exists.return_value=False
                return 'online'
            with patch.object(app,'login',side_effect=login):app.worker_loop()
            self.assertEqual(calls,['wifi-user','wired-user'])
            self.assertEqual(notice.call_count,2)

if __name__=='__main__':unittest.main()
