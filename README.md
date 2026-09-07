# BTC HD Wallet Monitor

Docker-first Bitcoin HD wallet address monitor for **wallets you control**.

This project creates or restores one BIP39 wallet, encrypts the derived BIP39 seed with Argon2id + AES-256-GCM, derives BIP44 Legacy Bitcoin addresses (`m/44'/0'/0'/0/i`), stores address/balance state in SQLite, checks balances through mempool.space, and sends a separate Telegram alert when an address becomes positive or its positive balance changes.

> Security boundary: this project does not brute-force random private keys or scan for third-party wallets. It only derives addresses from the wallet initialized or restored by the operator.

## Security model

- BIP39 24-word mnemonic generated once (or restored from your mnemonic).
- BIP39 seed is encrypted before being stored.
- KDF: Argon2id.
- Cipher: AES-256-GCM.
- SQLite stores `salt`, `nonce`, `ciphertext`, KDF parameters and wallet metadata.
- Master password is **never stored in SQLite**.
- Prefer Docker secret file / bind-mounted secret over plaintext environment variables.
- WIF private keys are derived only on demand from the decrypted seed and are not stored in the address table.

### Encryption / decryption flow

Encryption:

```text
MASTER PASSWORD + random salt
        | Argon2id
        v
32-byte AES key
        |
BIP39 seed + random 12-byte nonce + fixed AAD
        | AES-256-GCM
        v
ciphertext -> SQLite
```

Decryption:

```text
SQLite salt + MASTER PASSWORD
        | Argon2id (same parameters)
        v
same 32-byte AES key
        |
SQLite nonce + ciphertext + same AAD
        | AES-256-GCM
        v
original BIP39 seed
```

A wrong password, modified ciphertext, wrong nonce or wrong AAD causes AES-GCM authentication to fail.

## Files persisted in SQLite

`wallet_secret`:
- encrypted seed ciphertext
- nonce
- salt
- Argon2id parameters
- cipher/KDF version

`wallet_addresses`:
- derivation path
- P2PKH Base58Check address
- compressed public key
- balance in satoshis
- tx count
- last checked time
- last notified positive balance

## Docker deployment

```bash
cp .env.example .env
mkdir -p data secrets
printf '%s' 'USE-A-STRONG-UNIQUE-PASSWORD' > secrets/master_password
chmod 600 secrets/master_password
```

Set Telegram values in `.env` if wanted, then build:

```bash
docker compose build
```

### Initialize a new wallet

This prints the mnemonic **once**. Back it up offline.

```bash
docker compose run --rm monitor init --count 20
```

### Restore an existing BIP39 wallet

```bash
docker compose run --rm monitor restore --count 20
```

You will be prompted for the mnemonic. Do not put it in shell history.

### Add more receive addresses

```bash
docker compose run --rm monitor derive --count 20
```

### Show address state

```bash
docker compose run --rm monitor list-addresses
```

### Export one WIF private key

```bash
docker compose run --rm monitor export-wif --index 0
```

The WIF is printed to stdout. Treat terminal scrollback as sensitive.

### Start monitoring

```bash
docker compose up -d monitor
```

Logs:

```bash
docker compose logs -f monitor
```

## Telegram

Set:

```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

The monitor alerts separately per address when:

1. balance changes from `0` to `> 0`, or
2. an already-positive balance changes.

It does not alert every scan when the balance is unchanged.

## Balance provider

Default provider is the public mempool.space REST API:

```dotenv
MEMPOOL_API_BASE=https://mempool.space/api
```

Confirmed balance is calculated as:

```text
chain_stats.funded_txo_sum - chain_stats.spent_txo_sum
```

Use a self-hosted mempool instance by changing the base URL.

## Backup and recovery

Back up both:

1. the offline BIP39 mnemonic (most important), and
2. `./data/wallet.db`.

The mnemonic alone can reconstruct the wallet. The encrypted DB additionally preserves monitor state. The DB without the correct master password cannot decrypt the stored seed.

Never keep the mnemonic, master-password file and database backup in the same place.

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Commands

```text
init [--count N]            create encrypted wallet and first N addresses
restore [--count N]         restore from a BIP39 mnemonic
derive [--count N]          derive N more addresses
list-addresses              print monitored addresses and balances
scan-once                   check all addresses once
monitor                     continuously scan
export-wif --index N        decrypt seed and derive one WIF private key
healthcheck                 verify SQLite is reachable
```

## Important operational notes

- Do not commit `.env`, `data/`, `secrets/`, wallet DBs, mnemonics or exported private keys.
- Use a long, unique master password. Losing both the mnemonic and master password makes encrypted seed recovery impossible.
- Public APIs can rate-limit. Increase `SCAN_INTERVAL_SECONDS` when monitoring many addresses or use your own mempool instance.
- SQLite permissions should be restricted to the container/service account.
