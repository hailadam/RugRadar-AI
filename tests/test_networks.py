import unittest
from dataclasses import FrozenInstanceError

from rugradar.networks import NETWORKS, address_key, get_network, validate_address


EVM_ADDRESS = "0x" + "aB" * 20
SOLANA_ADDRESS = "So11111111111111111111111111111111111111112"


class NetworkTests(unittest.TestCase):
    def test_supported_network_metadata(self):
        expected = {
            "base": 8453, "ethereum": 1, "bsc": 56, "arbitrum": 42161,
            "optimism": 10, "polygon": 137, "avalanche": 43114,
        }
        self.assertEqual(set(NETWORKS), set(expected) | {"solana"})
        for key, chain_id in expected.items():
            with self.subTest(network=key):
                network = get_network(key)
                self.assertEqual(network.chain_id, chain_id)
                self.assertEqual(network.goplus_chain_id, str(chain_id))
                self.assertTrue(network.evm)
                self.assertTrue(network.rpc_env.endswith("_RPC_URL"))
        self.assertFalse(get_network("solana").evm)
        self.assertIsNone(get_network("solana").goplus_chain_id)
        with self.assertRaises(FrozenInstanceError):
            get_network().key = "elsewhere"

    def test_networks_are_allowlisted(self):
        for network in ("unknown", "BASE", "../base", "base/other", "https://other", None, []):
            with self.subTest(network=network), self.assertRaises(ValueError):
                get_network(network)

    def test_evm_address_validation_and_key(self):
        for network in NETWORKS:
            if not get_network(network).evm:
                continue
            self.assertEqual(validate_address(" " + EVM_ADDRESS + " ", network), EVM_ADDRESS)
            self.assertEqual(address_key(EVM_ADDRESS, network), EVM_ADDRESS.lower())
        for address in ("", "0xabc", "0X" + "a" * 40, "0x" + "g" * 40, SOLANA_ADDRESS, None):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_address(address)

    def test_solana_addresses_keep_case(self):
        self.assertEqual(validate_address(" " + SOLANA_ADDRESS + " ", "solana"), SOLANA_ADDRESS)
        self.assertEqual(address_key(SOLANA_ADDRESS, "solana"), SOLANA_ADDRESS)
        self.assertEqual(validate_address("1" * 32, "solana"), "1" * 32)

    def test_solana_addresses_decode_to_exactly_32_bytes(self):
        for address in ("1" * 31, "1" * 33, "z" * 44, "1" * 31 + "0", "1" * 31 + "O",
                        "1" * 31 + "I", "1" * 31 + "l", EVM_ADDRESS, "a/b", ""):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_address(address, "solana")


if __name__ == "__main__":
    unittest.main()
