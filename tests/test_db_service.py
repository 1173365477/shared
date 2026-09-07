from dataclasses import dataclass

from btc_wallet_monitor.crypto import KdfParams, encrypt_seed
from btc_wallet_monitor.db import Database
from btc_wallet_monitor.providers import AddressStatus
from btc_wallet_monitor.service import MonitorService


class FakeProvider:
    def __init__(self, balance_sat: int):
        self.balance_sat = balance_sat
        self.seen = []

    def get_address_status(self, address: str) -> AddressStatus:
        self.seen.append(address)
        return AddressStatus(
            balance_sat=self.balance_sat,
            tx_count=1 if self.balance_sat else 0,
            confirmed_balance_sat=self.balance_sat,
            unconfirmed_delta_sat=0,
        )


@dataclass
class FakeNotifier:
    sent: list

    def send_balance_alert(self, address: str, balance_sat: int, derivation_path: str) -> bool:
        self.sent.append((address, balance_sat, derivation_path))
        return True


def test_db_roundtrip(tmp_path):
    db = Database(str(tmp_path / "wallet.db"))
    encrypted = encrypt_seed(
        b"seed",
        "a-very-long-test-password",
        KdfParams(time_cost=1, memory_cost_kib=8192, parallelism=1),
    )
    db.save_encrypted_seed(encrypted)
    db.insert_address(0, "m/44'/0'/0'/0/0", "1Example", "02" + "11" * 32)

    loaded = db.load_encrypted_seed()
    row = db.get_address_by_index(0)

    assert loaded.ciphertext == encrypted.ciphertext
    assert row.address == "1Example"
    assert row.balance_sat == 0


def test_positive_balance_alert_is_deduplicated(tmp_path):
    db = Database(str(tmp_path / "wallet.db"))
    db.init_schema()
    db.insert_address(0, "m/44'/0'/0'/0/0", "1Example", "02" + "11" * 32)
    notifier = FakeNotifier(sent=[])
    provider = FakeProvider(12345)
    service = MonitorService(db, provider, notifier, 60)

    service.scan_once()
    service.scan_once()

    assert notifier.sent == [("1Example", 12345, "m/44'/0'/0'/0/0")]
    assert db.get_address_by_index(0).balance_sat == 12345


def test_scan_address_scans_only_requested_row(tmp_path):
    db = Database(str(tmp_path / "wallet.db"))
    db.init_schema()
    db.insert_address(0, "m/44'/0'/0'/0/0", "1First", "02" + "11" * 32)
    db.insert_address(1, "m/44'/0'/0'/0/1", "1Second", "02" + "22" * 32)

    provider = FakeProvider(777)
    notifier = FakeNotifier(sent=[])
    service = MonitorService(db, provider, notifier, 60)

    row = db.get_address_by_index(1)
    assert service.scan_address(row) is True

    assert provider.seen == ["1Second"]
    assert db.get_address_by_index(0).balance_sat == 0
    assert db.get_address_by_index(1).balance_sat == 777
    assert notifier.sent == [("1Second", 777, "m/44'/0'/0'/0/1")]
