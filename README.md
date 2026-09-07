# BTC HD Wallet Monitor

Docker-first Bitcoin HD wallet address generator/monitor for **wallets you control**.

This project creates or restores one BIP39 wallet, encrypts the derived BIP39 seed with Argon2id + AES-256-GCM, derives BIP44 Legacy Bitcoin addresses (`m/44'/0'/0'/0/i`), stores address/balance state in SQLite, checks balances through mempool.space, and can send Telegram alerts.

> Security boundary: this project does not brute-force random private keys or scan for third-party wallets. It only derives addresses from the wallet initialized or restored by the operator.

## Default runtime behavior

The default Docker Compose service now does exactly this:

```text
Derive 1 new P2PKH address
        ↓
Store it in SQLite
        ↓
Scan only that new address once
        ↓
Persist balance / tx count
        ↓
If balance > 0, send Telegram alert
        ↓
Sleep 5 seconds
        ↓
Repeat forever
```

Historical addresses are **not automatically rescanned** by the default service.

When you want to rescan every stored address manually:

```bash
docker compose run --rm worker scan-all
```

`scan-once` is kept as a backward-compatible alias for the same full-wallet manual scan.

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
- derivation index/path
- P2PKH Base58Check address
- compressed public key
- last known balance in satoshis
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

Optional Telegram configuration in `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Default generation interval:

```dotenv
GENERATE_INTERVAL_SECONDS=5
```

Build:

```bash
docker compose build
```

### Initialize a new wallet

This prints the mnemonic **once**. Back it up offline.

```bash
docker compose run --rm worker init --count 1
```

### Restore an existing BIP39 wallet

```bash
docker compose run --rm worker restore --count 1
```

### Start the 5-second generator

```bash
docker compose up -d worker
```

Logs:

```bash
docker compose logs -f worker
```

### Derive and scan exactly one new address manually

```bash
docker compose run --rm worker derive-scan
```

### Manually scan all historical addresses

```bash
docker compose run --rm worker scan-all
```

### List stored addresses

```bash
docker compose run --rm worker list-addresses
```

### Export one WIF private key

```bash
docker compose run --rm worker export-wif --index 0
```

The WIF is printed to stdout. Treat terminal scrollback as sensitive.

## Balance provider

Default provider is the public mempool.space REST API:

```dotenv
MEMPOOL_API_BASE=https://mempool.space/api
```

Use a self-hosted mempool instance by changing the base URL.

## Backup and recovery

Back up both:

1. the offline BIP39 mnemonic (most important), and
2. `./data/wallet.db`.

The mnemonic alone can reconstruct the wallet. The encrypted DB additionally preserves monitor state. The DB without the correct master password cannot decrypt the stored seed.

Never keep the mnemonic, master-password file and database backup in the same place.

## Commands

```text
init [--count N]            create encrypted wallet and initial addresses
restore [--count N]         restore from a BIP39 mnemonic
derive [--count N]          derive addresses without scanning
derive-scan                 derive 1 new address and scan only it once
generate-forever            repeat derive-scan using GENERATE_INTERVAL_SECONDS
list-addresses              show stored addresses and last known balances
scan-all                    manually scan every stored address once
scan-once                   alias of scan-all
monitor                     legacy continuous full-wallet rescanner (not default)
export-wif --index N        decrypt seed and derive one WIF private key
healthcheck                 verify SQLite is reachable
```

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Important operational notes

- Do not commit `.env`, `data/`, `secrets/`, wallet DBs, mnemonics or exported private keys.
- Use a long, unique master password.
- Public APIs can rate-limit. A 5-second interval is one new-address lookup every 5 seconds; manual `scan-all` can generate many requests if the database is large.
- SQLite permissions should be restricted to the container/service account.
