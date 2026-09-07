from __future__ import annotations

import getpass
import logging
import time

import typer
from cryptography.exceptions import InvalidTag

from .config import load_settings, read_master_password
from .crypto import decrypt_seed, encrypt_seed
from .db import Database
from .providers import MempoolSpaceProvider
from .service import MonitorService
from .telegram import TelegramNotifier
from .wallet import derive_address, derive_wif, generate_mnemonic, mnemonic_to_seed

app = typer.Typer(no_args_is_help=True, help="Encrypted Bitcoin HD wallet address monitor")


def _db() -> Database:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init_schema()
    return db


def _password(confirm: bool = False) -> str:
    settings = load_settings()
    password = read_master_password(settings)
    if password is None:
        password = getpass.getpass("Master password: ")
        if confirm:
            second = getpass.getpass("Confirm master password: ")
            if password != second:
                raise typer.BadParameter("master passwords do not match")
    if len(password) < 16:
        raise typer.BadParameter("master password must be at least 16 characters")
    return password


def _decrypt_wallet(db: Database) -> bytes:
    password = _password()
    try:
        return decrypt_seed(db.load_encrypted_seed(), password)
    except InvalidTag as exc:
        raise typer.BadParameter("wrong master password or corrupted encrypted seed") from exc


def _derive_many(db: Database, seed: bytes, count: int) -> tuple[int, int]:
    if count < 1:
        raise typer.BadParameter("count must be >= 1")
    start = db.next_derivation_index()
    for index in range(start, start + count):
        item = derive_address(seed, index)
        db.insert_address(item.index, item.path, item.address, item.public_key_hex)
    return start, start + count - 1


def _derive_one(db: Database, seed: bytes):
    index = db.next_derivation_index()
    item = derive_address(seed, index)
    db.insert_address(item.index, item.path, item.address, item.public_key_hex)
    return db.get_address_by_index(index)


@app.command("init")
def init_wallet(count: int = typer.Option(1, min=1, max=10000)) -> None:
    """Create a new 24-word BIP39 wallet and encrypted seed store."""
    db = _db()
    if db.wallet_exists():
        raise typer.BadParameter("wallet already initialized")

    password = _password(confirm=True)
    mnemonic = generate_mnemonic()
    seed = mnemonic_to_seed(mnemonic)
    db.save_encrypted_seed(encrypt_seed(seed, password))
    start, end = _derive_many(db, seed, count)

    typer.echo("\nBACK UP THIS MNEMONIC OFFLINE. IT WILL NOT BE STORED IN PLAINTEXT:\n")
    typer.echo(mnemonic)
    typer.echo(f"\nInitialized addresses {start}..{end}.")


@app.command("restore")
def restore_wallet(count: int = typer.Option(1, min=1, max=10000)) -> None:
    """Restore a wallet from an operator-supplied BIP39 mnemonic."""
    db = _db()
    if db.wallet_exists():
        raise typer.BadParameter("wallet already initialized")

    mnemonic = getpass.getpass("BIP39 mnemonic (input hidden): ").strip()
    password = _password(confirm=True)
    try:
        seed = mnemonic_to_seed(mnemonic)
    except Exception as exc:
        raise typer.BadParameter("invalid BIP39 mnemonic") from exc

    db.save_encrypted_seed(encrypt_seed(seed, password))
    start, end = _derive_many(db, seed, count)
    typer.echo(f"Restored wallet and addresses {start}..{end}.")


@app.command("derive")
def derive_more(count: int = typer.Option(1, min=1, max=10000)) -> None:
    """Derive more P2PKH receive addresses without scanning them."""
    db = _db()
    seed = _decrypt_wallet(db)
    start, end = _derive_many(db, seed, count)
    typer.echo(f"Derived addresses {start}..{end}.")


@app.command("list-addresses")
def list_addresses() -> None:
    """Print stored addresses and their last known balance without exposing private keys."""
    db = _db()
    rows = db.list_addresses()
    typer.echo("index\tbalance_sat\ttx_count\tpath\taddress")
    for row in rows:
        typer.echo(
            f"{row.derivation_index}\t{row.balance_sat}\t{row.tx_count}\t"
            f"{row.derivation_path}\t{row.address}"
        )


def _service() -> MonitorService:
    settings = load_settings()
    db = Database(settings.db_path)
    db.init_schema()
    provider = MempoolSpaceProvider(settings.mempool_api_base, settings.request_timeout_seconds)
    notifier = TelegramNotifier(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        settings.request_timeout_seconds,
    )
    return MonitorService(db, provider, notifier, settings.scan_interval_seconds)


def _scan_new_address(db: Database, seed: bytes, service: MonitorService) -> bool:
    row = _derive_one(db, seed)
    typer.echo(
        f"Derived index={row.derivation_index} path={row.derivation_path} address={row.address}"
    )
    ok = service.scan_address(row)
    if not ok:
        typer.echo(
            f"Balance check failed for index={row.derivation_index}; address remains stored for a later manual scan.",
            err=True,
        )
    return ok


@app.command("derive-scan")
def derive_scan() -> None:
    """Derive exactly one new address and scan only that new address once."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = _db()
    seed = _decrypt_wallet(db)
    service = _service()
    _scan_new_address(db, seed, service)


@app.command("generate-forever")
def generate_forever() -> None:
    """Continuously derive one new address, scan only it once, then sleep."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    db = _db()
    seed = _decrypt_wallet(db)
    service = _service()

    typer.echo(
        f"Generator started: one new address every {settings.generate_interval_seconds:g} seconds"
    )
    while True:
        _scan_new_address(db, seed, service)
        time.sleep(settings.generate_interval_seconds)


@app.command("scan-all")
def scan_all() -> None:
    """Manually scan every stored address once."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _service().scan_once()


@app.command("scan-once")
def scan_once() -> None:
    """Backward-compatible alias: manually scan every stored address once."""
    scan_all()


@app.command("monitor")
def monitor() -> None:
    """Legacy command: continuously rescan all stored addresses."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _service().run_forever()


@app.command("export-wif")
def export_wif(index: int = typer.Option(..., min=0)) -> None:
    """Decrypt the seed and export one stored address private key in compressed WIF."""
    db = _db()
    row = db.get_address_by_index(index)
    seed = _decrypt_wallet(db)
    derived = derive_address(seed, index)
    if derived.address != row.address:
        raise RuntimeError("derived address does not match database; refusing to export")
    typer.echo(derive_wif(seed, index))


@app.command("healthcheck")
def healthcheck() -> None:
    """Return success when SQLite is accessible."""
    if not _db().ping():
        raise typer.Exit(code=1)
    typer.echo("ok")


if __name__ == "__main__":
    app()
