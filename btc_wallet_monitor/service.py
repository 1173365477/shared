from __future__ import annotations

import logging
import time

from .db import AddressRow, Database
from .providers import MempoolSpaceProvider
from .telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(
        self,
        db: Database,
        provider: MempoolSpaceProvider,
        notifier: TelegramNotifier,
        interval_seconds: int,
    ):
        self.db = db
        self.provider = provider
        self.notifier = notifier
        self.interval_seconds = interval_seconds

    def scan_address(self, row: AddressRow) -> bool:
        """Scan one already-derived address and persist its latest state."""
        try:
            status = self.provider.get_address_status(row.address)
            self.db.update_scan(row.address, status.balance_sat, status.tx_count)

            if status.balance_sat > 0 and status.balance_sat != row.last_notified_balance_sat:
                logger.warning(
                    "Positive balance detected address=%s balance_sat=%d path=%s",
                    row.address,
                    status.balance_sat,
                    row.derivation_path,
                )
                if self.notifier.send_balance_alert(
                    row.address, status.balance_sat, row.derivation_path
                ):
                    self.db.mark_notified(row.address, status.balance_sat)
            elif status.balance_sat == 0 and row.last_notified_balance_sat != 0:
                self.db.mark_notified(row.address, 0)

            logger.info(
                "Scanned address index=%d address=%s balance_sat=%d tx_count=%d",
                row.derivation_index,
                row.address,
                status.balance_sat,
                status.tx_count,
            )
            return True
        except Exception as exc:
            logger.exception("Failed scanning address=%s error=%s", row.address, exc)
            return False

    def scan_once(self) -> None:
        """Manually scan every address currently stored in SQLite once."""
        rows = self.db.list_addresses()
        logger.info("Scanning %d addresses", len(rows))
        for row in rows:
            self.scan_address(row)

    def run_forever(self) -> None:
        """Legacy continuous full-wallet monitor; not used by default Compose service."""
        logger.info("Monitor started interval=%ss", self.interval_seconds)
        while True:
            self.scan_once()
            time.sleep(self.interval_seconds)
