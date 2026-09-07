from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .crypto import EncryptedSeed, KdfParams


@dataclass(frozen=True)
class AddressRow:
    id: int
    derivation_index: int
    derivation_path: str
    address: str
    public_key_hex: str
    balance_sat: int
    tx_count: int
    last_checked_at: str | None
    last_notified_balance_sat: int


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS wallet_secret (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    ciphertext BLOB NOT NULL,
                    nonce BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    kdf_name TEXT NOT NULL DEFAULT 'argon2id',
                    cipher_name TEXT NOT NULL DEFAULT 'aes-256-gcm',
                    time_cost INTEGER NOT NULL,
                    memory_cost_kib INTEGER NOT NULL,
                    parallelism INTEGER NOT NULL,
                    hash_len INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS wallet_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    derivation_index INTEGER NOT NULL UNIQUE,
                    derivation_path TEXT NOT NULL UNIQUE,
                    address TEXT NOT NULL UNIQUE,
                    public_key_hex TEXT NOT NULL,
                    balance_sat INTEGER NOT NULL DEFAULT 0,
                    tx_count INTEGER NOT NULL DEFAULT 0,
                    last_checked_at TEXT,
                    last_notified_balance_sat INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_wallet_addresses_address
                ON wallet_addresses(address);

                CREATE INDEX IF NOT EXISTS idx_wallet_addresses_balance
                ON wallet_addresses(balance_sat);
                """
            )

    def wallet_exists(self) -> bool:
        self.init_schema()
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM wallet_secret WHERE id = 1").fetchone() is not None

    def save_encrypted_seed(self, record: EncryptedSeed) -> None:
        self.init_schema()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO wallet_secret (
                    id, ciphertext, nonce, salt, time_cost, memory_cost_kib,
                    parallelism, hash_len, version, created_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.ciphertext,
                    record.nonce,
                    record.salt,
                    record.params.time_cost,
                    record.params.memory_cost_kib,
                    record.params.parallelism,
                    record.params.hash_len,
                    record.version,
                    now,
                ),
            )

    def load_encrypted_seed(self) -> EncryptedSeed:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM wallet_secret WHERE id = 1").fetchone()
        if row is None:
            raise RuntimeError("wallet is not initialized")
        return EncryptedSeed(
            ciphertext=row["ciphertext"],
            nonce=row["nonce"],
            salt=row["salt"],
            params=KdfParams(
                time_cost=row["time_cost"],
                memory_cost_kib=row["memory_cost_kib"],
                parallelism=row["parallelism"],
                hash_len=row["hash_len"],
            ),
            version=row["version"],
        )

    def next_derivation_index(self) -> int:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(derivation_index) AS max_i FROM wallet_addresses").fetchone()
        return 0 if row["max_i"] is None else int(row["max_i"]) + 1

    def insert_address(self, derivation_index: int, derivation_path: str, address: str, public_key_hex: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO wallet_addresses (
                    derivation_index, derivation_path, address, public_key_hex, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (derivation_index, derivation_path, address, public_key_hex, now),
            )

    def list_addresses(self) -> list[AddressRow]:
        self.init_schema()
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM wallet_addresses ORDER BY derivation_index").fetchall()
        return [AddressRow(**dict(row)) for row in rows]

    def get_address_by_index(self, index: int) -> AddressRow:
        self.init_schema()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM wallet_addresses WHERE derivation_index = ?", (index,)
            ).fetchone()
        if row is None:
            raise KeyError(f"address index {index} not found")
        return AddressRow(**dict(row))

    def update_scan(self, address: str, balance_sat: int, tx_count: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE wallet_addresses
                SET balance_sat = ?, tx_count = ?, last_checked_at = ?
                WHERE address = ?
                """,
                (balance_sat, tx_count, now, address),
            )

    def mark_notified(self, address: str, balance_sat: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE wallet_addresses SET last_notified_balance_sat = ? WHERE address = ?",
                (balance_sat, address),
            )

    def ping(self) -> bool:
        self.init_schema()
        with self.connect() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
