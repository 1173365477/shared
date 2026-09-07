from __future__ import annotations

import os
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"btc-hd-wallet-monitor:seed:v1"


@dataclass(frozen=True)
class KdfParams:
    time_cost: int = 3
    memory_cost_kib: int = 262144
    parallelism: int = 2
    hash_len: int = 32


@dataclass(frozen=True)
class EncryptedSeed:
    ciphertext: bytes
    nonce: bytes
    salt: bytes
    params: KdfParams
    version: int = 1


def derive_key(password: str, salt: bytes, params: KdfParams) -> bytes:
    if not password:
        raise ValueError("master password must not be empty")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost_kib,
        parallelism=params.parallelism,
        hash_len=params.hash_len,
        type=Type.ID,
    )


def encrypt_seed(seed: bytes, password: str, params: KdfParams | None = None) -> EncryptedSeed:
    if not seed:
        raise ValueError("seed must not be empty")
    params = params or KdfParams()
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(password, salt, params)
    ciphertext = AESGCM(key).encrypt(nonce, seed, AAD)
    return EncryptedSeed(ciphertext=ciphertext, nonce=nonce, salt=salt, params=params)


def decrypt_seed(record: EncryptedSeed, password: str) -> bytes:
    key = derive_key(password, record.salt, record.params)
    return AESGCM(key).decrypt(record.nonce, record.ciphertext, AAD)
