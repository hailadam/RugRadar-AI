import unittest
from unittest.mock import Mock
import httpx
from rugradar.market import (DataSourceError, fetch_pairs, snapshot_from_pairs, validate_address)

ADDRESS = '0x' + 'a' * 40
PAIR = '0x' + 'b' * 40


def pair(**changes):
    result = {
        'chainId': 'base', 'pairAddress': PAIR, 'dexId': 'uniswap',
        'baseToken': {'address': ADDRESS, 'name': 'Example', 'symbol': 'EXP'},
        'quoteToken': {'address': '0x'+'c'*40, 'name':'USD Coin', 'symbol':'USDC'},
        'priceUsd':'0.123', 'liquidity':{'usd':9000}, 'volume':{'h24':10000},
        'priceChange':{'h24':-80}, 'txns':{'h24':{'buys':5,'sells':44}}
    }
    result.update(changes)
    return result


class MarketTests(unittest.TestCase):
    def test_address_validation(self):
        self.assertEqual(validate_address(' '+ADDRESS+' '), ADDRESS)
        for wrong in ('', 'abc', '0xabc', '0x'+'g'*40):
            with self.assertRaises(ValueError):
                validate_address(wrong)

    def test_pair_parsing(self):
        snap = snapshot_from_pairs(ADDRESS, [pair()])
        self.assertEqual(snap.symbol, 'EXP')
        self.assertEqual(snap.price_usd, 0.123)
        self.assertEqual(snap.liquidity_usd, 9000)
        self.assertEqual(snap.sells_h24, 44)

    def test_quote_only_does_not_assign_wrong_price(self):
        data = pair(baseToken={'address':'0x'+'c'*40}, quoteToken={'address':ADDRESS, 'name':'Example', 'symbol':'EXP'})
        snap = snapshot_from_pairs(ADDRESS, [data])
        self.assertIsNone(snap.price_usd)
        self.assertFalse(snap.price_is_available)

    def test_pair_filtering_prevents_cross_chain_data(self):
        response = Mock()
        response.json.return_value = [pair(), pair(chainId='solana'), pair(baseToken={'address':'0x'+'d'*40})]
        response.raise_for_status.return_value = None
        client = Mock()
        client.get.return_value = response
        self.assertEqual(len(fetch_pairs(ADDRESS, client)), 1)

    def test_api_failure_is_not_silent(self):
        client = Mock()
        client.get.side_effect = httpx.TimeoutException('timeout')
        with self.assertRaises(DataSourceError):
            fetch_pairs(ADDRESS, client)
