from __future__ import annotations

import hashlib
from dataclasses import dataclass

from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip39WordsNum, Bip44, Bip44Changes, Bip44Coins

ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class DerivedAddress:
    index: int
    path: str
    address: str
    public_key_hex: str


def generate_mnemonic() -> str:
    return str(Bip39MnemonicGenerator().FromWordsNumber(Bip39WordsNum.WORDS_NUM_24))


def mnemonic_to_seed(mnemonic: str) -> bytes:
    return Bip39SeedGenerator(mnemonic).Generate()


def _node_for_index(seed: bytes, index: int):
    if index < 0:
        raise ValueError("index must be >= 0")
    root = Bip44.FromSeed(seed, Bip44Coins.BITCOIN)
    return root.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)


def derive_address(seed: bytes, index: int) -> DerivedAddress:
    node = _node_for_index(seed, index)
    return DerivedAddress(
        index=index,
        path=f"m/44'/0'/0'/0/{index}",
        address=node.PublicKey().ToAddress(),
        public_key_hex=node.PublicKey().RawCompressed().ToHex(),
    )


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = bytearray()
    while number:
        number, remainder = divmod(number, 58)
        encoded.append(ALPHABET[remainder])
    encoded.reverse()
    leading_zeroes = len(raw) - len(raw.lstrip(b"\x00"))
    return (ALPHABET[:1] * leading_zeroes + encoded).decode("ascii")


def _base58check(payload: bytes) -> str:
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return _b58encode(payload + checksum)


def derive_wif(seed: bytes, index: int) -> str:
    node = _node_for_index(seed, index)
    private_key = node.PrivateKey().Raw().ToBytes()
    return _base58check(b"\x80" + private_key + b"\x01")
