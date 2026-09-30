import importlib.util
from pathlib import Path
import unittest
import logging
from unittest.mock import patch
from urllib.parse import parse_qs

import portable_app as app


class Tests(unittest.TestCase):
    def test_windows_dpapi_roundtrip(self):
        secret = b'fictional-test-account-and-password'
        encrypted = app.protect(secret)
        self.assertNotIn(secret, encrypted)
        self.assertEqual(app.protect(encrypted, decrypt=True), secret)

    def test_does_not_send_credentials_to_unrecognized_page(self):
        with patch.object(app, 'request', return_value=(200, '<html>ordinary router</html>', {})) as req:
            self.assertEqual(app.login('10.0.0.1', {}), 'portal_unavailable')
            self.assertEqual(req.call_count, 2)

    def test_telecom_request_and_verified_success(self):
        with patch.object(app, 'request', side_effect=[(200, 'eportal', {}), (302, '')]) as req, \
             patch.object(app, 'online', return_value=True), patch.object(app.time, 'sleep'):
            self.assertEqual(app.login('10.0.0.1', {'username': 'test@telecom', 'password': 'a&+=中'}), 'online')
            call = req.call_args
            fields = parse_qs(call.kwargs['body'].decode())
            self.assertEqual(fields['DDDDD'], [',0,test@telecom'])
            self.assertEqual(fields['upass'], ['a&+=中'])
            self.assertEqual(call.kwargs['port'], 801)

    def test_redirect_alone_is_not_success(self):
        with patch.object(app, 'request', side_effect=[(200, 'drcom', {}), (302, '')]), \
             patch.object(app, 'online', return_value=False), patch.object(app.time, 'sleep'):
            self.assertEqual(app.login('10.0.0.1', {'username': 'test', 'password': 'dummy'}), 'authentication_unverified')

    def test_captive_page_is_not_internet(self):
        with patch.object(app, 'request', return_value=(200, 'Please login')):
            self.assertFalse(app.online('10.0.0.1'))

    def test_connection_bound_to_wired_ip(self):
        with patch.object(app.http.client, 'HTTPConnection') as conn:
            conn.return_value.getresponse.return_value.read.return_value = b'OK'
            app.request('10.1.2.3', '172.16.2.100', '/')
            self.assertEqual(conn.call_args.kwargs['source_address'], ('10.1.2.3', 0))

    def test_retries_stop_after_five_unverified_submissions(self):
        states = []
        def state(code):
            states.append(code)
            if code == 'retry_limit':
                raise KeyboardInterrupt()
        with patch.object(app, 'CONFIG') as config, \
             patch.object(app, 'protect', return_value=b'{"username":"test","password":"dummy"}'), \
             patch.object(app, 'wired_ip', return_value='10.0.0.1'), \
             patch.object(app, 'online', return_value=False), \
             patch.object(app, 'login', return_value='authentication_unverified') as login, \
             patch.object(app, 'set_state', side_effect=state), \
             patch.object(app, 'RotatingFileHandler', return_value=logging.NullHandler()), \
             patch.object(app.time, 'sleep'), patch.object(app.time, 'monotonic', side_effect=range(0, 100000, 1000)):
            config.exists.return_value = True
            config.stat.return_value.st_mtime_ns = 1
            with self.assertRaises(KeyboardInterrupt):
                app.worker_loop()
            self.assertEqual(login.call_count, 5)
            self.assertEqual(states[-1], 'retry_limit')


if __name__ == '__main__':
    unittest.main()


