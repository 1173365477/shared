import pytest
from cryptography.exceptions import InvalidTag

from btc_wallet_monitor.crypto import KdfParams, decrypt_seed, encrypt_seed
from btc_wallet_monitor.wallet import derive_address, derive_wif, mnemonic_to_seed

MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


def fast_params() -> KdfParams:
    return KdfParams(time_cost=1, memory_cost_kib=8192, parallelism=1)


def test_seed_encrypt_decrypt_roundtrip():
    seed = b"test-seed-bytes" * 4
    encrypted = encrypt_seed(seed, "a-very-long-test-password", fast_params())
    assert encrypted.ciphertext != seed
    assert decrypt_seed(encrypted, "a-very-long-test-password") == seed


def test_wrong_password_fails_authenticated_decryption():
    encrypted = encrypt_seed(b"secret-seed", "correct-password-123", fast_params())
    with pytest.raises(InvalidTag):
        decrypt_seed(encrypted, "incorrect-password-456")


def test_bip44_legacy_address_is_deterministic():
    seed = mnemonic_to_seed(MNEMONIC)
    first = derive_address(seed, 0)
    again = derive_address(seed, 0)
    assert first.address == again.address
    assert first.address == "1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA"
    assert first.path == "m/44'/0'/0'/0/0"
    assert len(first.public_key_hex) == 66


def test_compressed_mainnet_wif_shape():
    seed = mnemonic_to_seed(MNEMONIC)
    wif = derive_wif(seed, 0)
    assert wif[0] in ("K", "L")
    assert len(wif) == 52
