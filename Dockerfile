FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/wallet.db

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

COPY pyproject.toml README.md ./
COPY btc_wallet_monitor ./btc_wallet_monitor

RUN pip install --no-cache-dir .

USER appuser

ENTRYPOINT ["btc-wallet-monitor"]
CMD ["monitor"]
