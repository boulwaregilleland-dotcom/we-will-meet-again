import threading
import time
import unittest
from unittest.mock import patch
import portable_app as app
import success_notice


class SpeedTests(unittest.TestCase):
    def test_fast_probe_does_not_wait_for_slow_probe(self):
        release=threading.Event()
        slow_started=threading.Event()
        def request(ip,host,path,**kwargs):
            if 'msft' in host:
                slow_started.set()
                release.wait(3)
                return 200,'captive login'
            return 200,'success'
        try:
            with patch.object(app,'request',side_effect=request):
                start=time.monotonic()
                self.assertTrue(app.online('10.0.0.1'))
                self.assertLess(time.monotonic()-start,.8)
        finally:
            release.set()

    def test_login_success_has_no_fixed_sleep(self):
        with patch.object(app,'portal_context',return_value=(200,'eportal',dict(wlanacip='a',wlanacname='b'))), \
             patch.object(app,'request',return_value=(200,'ok')),patch.object(app,'online',return_value=True), \
             patch.object(app.time,'sleep') as sleep:
            self.assertEqual(app.login('10.0.0.1',dict(username='u',password='p')),'online')
            sleep.assert_not_called()

    def test_dialog_does_not_wait_for_browser_cleanup(self):
        release=threading.Event()
        def cleanup(app):release.wait(3)
        def dialog(*args,**kwargs):
            self.assertFalse(release.is_set())
            release.set()
        try:
            with patch.object(success_notice,'cleanup',side_effect=cleanup), \
                 patch.object(success_notice.messagebox,'showinfo',side_effect=dialog) as show:
                success_notice.run(app)
                show.assert_called_once()
        finally:
            release.set()


if __name__=='__main__':unittest.main()
