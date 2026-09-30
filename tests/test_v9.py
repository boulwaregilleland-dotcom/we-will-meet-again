import json
import unittest
from unittest.mock import patch
import portable_app as app
import success_notice


class SuccessTests(unittest.TestCase):
    def test_one_notice_per_connected_period(self):
        cfg=json.dumps(dict(username='fiction',password='fake',reconnect=True)).encode()
        seen=[]
        with patch.object(app,'CONFIG') as config, patch.object(app,'protect',return_value=cfg), \
             patch.object(app,'wired_ip',return_value='10.3.4.5'), \
             patch.object(app,'online',side_effect=[True,True,False,True]), \
             patch.object(app,'login',return_value='authentication_unverified'), \
             patch.object(app,'notify_success') as notice, patch.object(app.time,'sleep'), \
             patch.object(app,'RotatingFileHandler',return_value=app.logging.NullHandler()):
            config.exists.return_value=True
            config.stat.return_value.st_mtime_ns=1
            def state(code):
                seen.append(code)
                if seen.count('online')==3:
                    config.exists.return_value=False
            with patch.object(app,'set_state',side_effect=state):
                app.worker_loop()
            self.assertEqual(notice.call_count,2)

    def test_failed_authentication_never_notifies(self):
        with patch.object(app,'CONFIG') as config, \
             patch.object(app,'protect',return_value=b'{"username":"fiction","password":"fake"}'), \
             patch.object(app,'wired_ip',return_value='10.3.4.5'), patch.object(app,'online',return_value=False), \
             patch.object(app,'login',return_value='credentials_rejected'), patch.object(app,'notify_success') as notice, \
             patch.object(app,'RotatingFileHandler',return_value=app.logging.NullHandler()), patch.object(app.time,'sleep'):
            config.exists.return_value=True
            def state(code):
                if code=='credentials_rejected':config.exists.return_value=False
            with patch.object(app,'set_state',side_effect=state):app.worker_loop()
            notice.assert_not_called()

    def test_cleanup_failure_does_not_hide_success_dialog(self):
        with patch.object(success_notice,'close_portal_once',side_effect=OSError), \
             patch.object(success_notice.messagebox,'showinfo') as dialog:
            success_notice.run(app)
            dialog.assert_called_once()
            self.assertIn('网络验证成功',dialog.call_args.args[1])


if __name__=='__main__':unittest.main()
