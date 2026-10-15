import unittest
from unittest.mock import Mock
from rugradar.market import DataSourceError
from rugradar.security import fetch_security, is_flagged

ADDR = '0x' + 'a'*40


class SecurityTests(unittest.TestCase):
    def test_flag_parsing(self):
        self.assertTrue(is_flagged('1'))
        self.assertFalse(is_flagged('0'))
        self.assertFalse(is_flagged(None))

    def test_valid_data(self):
        response = Mock()
        response.json.return_value = {'code': 1, 'result': {ADDR: {'is_honeypot': '0'}}}
        client = Mock()
        client.get.return_value = response
        self.assertEqual(fetch_security(ADDR, client), {'is_honeypot': '0'})

    def test_unavailable_data(self):
        response = Mock()
        response.json.return_value = {'code': 0, 'message': 'denied'}
        client = Mock()
        client.get.return_value = response
        with self.assertRaises(DataSourceError):
            fetch_security(ADDR, client)
