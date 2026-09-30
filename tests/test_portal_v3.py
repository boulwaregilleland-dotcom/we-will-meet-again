import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import portable_app as app


class PortalTests(unittest.TestCase):
    def test_actual_ip_overrides_old_redirect_parameters(self):
        target = 'http://172.16.2.100/a70.htm?wlanuserip=10.16.158.237&ip=10.16.158.237&wlanacip=172.16.1.2&wlanacname=ecjtu_nic_ME60'
        with patch.object(app, 'request', side_effect=[(302, '', {'location': target}), (200, 'eportal', {})]) as req:
            status, _, params = app.portal_context('172.16.85.99')
            self.assertEqual(status, 200)
            query = parse_qs(urlsplit(req.call_args.args[2]).query)
            self.assertEqual(query['ip'], ['172.16.85.99'])
            self.assertEqual(query['wlanuserip'], ['172.16.85.99'])
            self.assertEqual(params['wlanacname'], 'ecjtu_nic_ME60')

    def test_external_redirect_never_receives_login(self):
        with patch.object(app, 'request', return_value=(302, '', {'location': 'http://example.com/a70.htm'})) as req:
            self.assertEqual(app.login('10.0.0.1', {'username': 'dummy', 'password': 'dummy'}), 'portal_unavailable')
            self.assertEqual(req.call_count, 1)

    def test_a70_fallback_uses_user_provided_controller_only(self):
        with patch.object(app, 'request', side_effect=[(404, '', {}), (200, 'drcom', {})]) as req:
            self.assertEqual(app.portal_context('10.20.30.40')[0], 200)
            path = req.call_args.args[2]
            self.assertTrue(path.startswith('/a70.htm?'))
            query = parse_qs(urlsplit(path).query)
            self.assertEqual(query['wlanacip'], ['172.16.1.2'])
            self.assertEqual(query['ip'], ['10.20.30.40'])

    def test_school_login_has_no_operator_suffix(self):
        with patch.object(app, 'request', side_effect=[(200, 'eportal', {}), (302, '')]) as req, \
             patch.object(app, 'online', return_value=True), patch.object(app.time, 'sleep'):
            app.login('172.16.85.99', {'username': 'test@telecom', 'password': 'test', 'service': 'campus'})
            form = parse_qs(req.call_args.kwargs['body'].decode())
            self.assertEqual(form['DDDDD'], [',0,test'])
            query = parse_qs(urlsplit(req.call_args.args[2]).query)
            self.assertEqual(query['wlanacip'], ['172.16.1.2'])


if __name__ == '__main__':
    unittest.main()
