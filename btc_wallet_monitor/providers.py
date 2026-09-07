from __future__ import annotations

from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class AddressStatus:
    balance_sat: int
    tx_count: int
    confirmed_balance_sat: int
    unconfirmed_delta_sat: int


class MempoolSpaceProvider:
    def __init__(self, base_url: str, timeout_seconds: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "btc-hd-wallet-monitor/1.0"})

    def get_address_status(self, address: str) -> AddressStatus:
        response = self.session.get(
            f"{self.base_url}/address/{address}", timeout=self.timeout_seconds
        )
        response.raise_for_status()
        payload = response.json()

        chain = payload.get("chain_stats") or {}
        mempool = payload.get("mempool_stats") or {}

        confirmed = int(chain.get("funded_txo_sum", 0)) - int(chain.get("spent_txo_sum", 0))
        unconfirmed_delta = int(mempool.get("funded_txo_sum", 0)) - int(
            mempool.get("spent_txo_sum", 0)
        )
        balance = confirmed + unconfirmed_delta
        tx_count = int(chain.get("tx_count", 0)) + int(mempool.get("tx_count", 0))

        return AddressStatus(
            balance_sat=max(0, balance),
            tx_count=tx_count,
            confirmed_balance_sat=max(0, confirmed),
            unconfirmed_delta_sat=unconfirmed_delta,
        )
