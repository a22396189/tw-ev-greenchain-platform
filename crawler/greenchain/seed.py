"""
One-time initialisation: create tables, load the seed CSVs, and try to backfill
history for the data that has a real historical API (share price, institutional
flows).

    docker compose run --rm crawler python -m greenchain.seed

Everything writes through upsert, so re-running this script is safe (rebuilding
the environment, or not remembering whether it already ran) - no duplicates,
no errors.

Set SEED_SKIP_LIVE_BACKFILL=1 to load only the CSVs and skip every network call
(useful for offline / sandbox testing).
"""
import csv
import os
from datetime import date, timedelta

from loguru import logger

from .db import ensure_tables, get_connection, load_stock_ids, upsert
from .sources import (
    institutional_investor,
    monthly_revenue,
    quarterly_margins,
    stock_price,
)

SEED_DIR = os.environ.get("SEED_DIR", "/app/data_seed")

# Backfill windows (env-overridable). Defaults keep the first run to a few
# minutes: ~6 months of price data across ~13 stocks, ~30 days of flows.
STOCK_PRICE_BACKFILL_MONTHS = int(os.environ.get("STOCK_PRICE_BACKFILL_MONTHS", "6"))
INSTITUTIONAL_BACKFILL_DAYS = int(os.environ.get("INSTITUTIONAL_BACKFILL_DAYS", "30"))


def _read_csv(filename):
    path = os.path.join(SEED_DIR, filename)
    if not os.path.exists(path):
        logger.warning(f"[seed] seed file not found: {path}; skipping")
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _coerce(row, int_fields=(), float_fields=()):
    out = dict(row)
    for k in int_fields:
        if out.get(k) not in (None, ""):
            out[k] = int(float(out[k]))
    for k in float_fields:
        if out.get(k) not in (None, ""):
            out[k] = float(out[k])
    # normalise empty strings to NULL
    for k, v in list(out.items()):
        if v == "":
            out[k] = None
    return out


def seed_dimension_and_targets(conn):
    """Data with no structured API - the tracked universe, and national energy targets."""
    rows = _read_csv("supply_chain_company.csv")
    n = upsert(conn, "supply_chain_company", rows)
    logger.info(f"[seed] supply_chain_company: {n} rows (this defines the analysed universe)")

    rows = _read_csv("green_energy_targets.csv")
    rows = [_coerce(r, int_fields=["Year"], float_fields=["TargetValue", "ActualValue"]) for r in rows]
    n = upsert(conn, "green_energy_targets", rows)
    logger.info(
        f"[seed] green_energy_targets: {n} rows "
        f"(ILLUSTRATIVE figures - verify each against its SourceURL before use)"
    )


def seed_financial_history(conn):
    """Data with a live API that only serves the newest period - pad history from CSV."""
    rows = _read_csv("quarterly_margins_seed.csv")
    rows = [_coerce(r, int_fields=["Year", "Quarter"],
                    float_fields=["GrossMarginPct", "OperatingMarginPct", "NetMarginPct"]) for r in rows]
    n = upsert(conn, "quarterly_margins", rows)
    logger.info(f"[seed] quarterly_margins (history baseline): {n} rows")

    rows = _read_csv("monthly_revenue_seed.csv")
    rows = [_coerce(r, int_fields=["RevenueThousandNTD"], float_fields=["YoYPct"]) for r in rows]
    n = upsert(conn, "monthly_revenue", rows)
    logger.info(f"[seed] monthly_revenue (history baseline): {n} rows")


def backfill_live_history(conn, stock_ids):
    """Data whose API can serve a historical range - hit the real TWSE endpoints."""
    today = date.today()
    y, m = today.year, today.month
    y -= STOCK_PRICE_BACKFILL_MONTHS // 12
    m -= STOCK_PRICE_BACKFILL_MONTHS % 12
    if m <= 0:
        m += 12
        y -= 1
    start_month = f"{y:04d}-{m:02d}"
    end_month = f"{today.year:04d}-{today.month:02d}"

    logger.info(
        f"[seed] backfilling share price {start_month}..{end_month} for {len(stock_ids)} stocks "
        f"(real TWSE API, a few minutes - please wait)"
    )
    try:
        rows = stock_price.fetch_range(stock_ids, start_month, end_month)
        n = upsert(conn, "stock_price", rows)
        logger.info(f"[OK][seed] stock_price backfill: {n} rows (TWSE STOCK_DAY, live)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[seed] share-price backfill failed ({e}); daily Airflow task will keep trying.")

    inst_start = today - timedelta(days=INSTITUTIONAL_BACKFILL_DAYS)
    logger.info(
        f"[seed] backfilling institutional flows: last {INSTITUTIONAL_BACKFILL_DAYS} days "
        f"(real TWSE API, day-by-day, slower)"
    )
    try:
        rows = institutional_investor.fetch_range(stock_ids, inst_start.isoformat(), today.isoformat())
        n = upsert(conn, "institutional_investor", rows)
        logger.info(f"[OK][seed] institutional_investor backfill: {n} rows (TWSE T86, live)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[seed] institutional-flow backfill failed ({e}).")

    logger.info("[seed] trying latest live quarter margins / latest live month revenue ...")
    try:
        rows = quarterly_margins.fetch_latest(stock_ids)
        if rows:
            upsert(conn, "quarterly_margins", rows)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[seed] latest-quarter margins failed ({e}); keeping seed history.")

    try:
        rows = monthly_revenue.fetch_latest(stock_ids)
        if rows:
            upsert(conn, "monthly_revenue", rows)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[seed] latest-month revenue failed ({e}); keeping seed history.")


def main():
    logger.info("=== TW EV & Green-Energy supply-chain platform: DB init / backfill ===")
    conn = get_connection()
    ensure_tables(conn)
    logger.info("[seed] tables ensured")

    seed_dimension_and_targets(conn)
    seed_financial_history(conn)

    stock_ids = load_stock_ids(conn)

    if os.environ.get("SEED_SKIP_LIVE_BACKFILL", "").lower() in ("1", "true", "yes"):
        logger.info("[seed] SEED_SKIP_LIVE_BACKFILL set; skipping live backfill (offline mode)")
    else:
        backfill_live_history(conn, stock_ids)

    conn.close()
    logger.info("=== init complete ===")


if __name__ == "__main__":
    main()
