"""
CLI entry point - called by the Airflow PythonOperator, and usable by hand
inside the container for testing a single task:

    python -m greenchain.main stock_price
    python -m greenchain.main institutional_investor
    python -m greenchain.main quarterly_margins
    python -m greenchain.main monthly_revenue
    python -m greenchain.main all
"""
import sys

from loguru import logger

from .db import ensure_tables, get_connection, load_stock_ids, upsert
from .sources import (
    institutional_investor,
    monthly_revenue,
    quarterly_margins,
    stock_price,
)

TASKS = {
    "stock_price": ("stock_price", stock_price.fetch_latest),
    "institutional_investor": ("institutional_investor", institutional_investor.fetch_latest),
    "quarterly_margins": ("quarterly_margins", quarterly_margins.fetch_latest),
    "monthly_revenue": ("monthly_revenue", monthly_revenue.fetch_latest),
}


def run_task(task_name: str) -> int:
    if task_name not in TASKS:
        raise ValueError(f"unknown task: {task_name}; available: {list(TASKS)}")

    table, fetch_fn = TASKS[task_name]
    conn = get_connection()
    try:
        ensure_tables(conn)
        stock_ids = load_stock_ids(conn)
        logger.info(f"[{task_name}] universe = {stock_ids}")
        rows = fetch_fn(stock_ids)
        n = upsert(conn, table, rows)
        if n == 0:
            logger.info(
                f"[{task_name}] nothing written this run "
                f"(connection failure, or TWSE has not updated yet - both normal)"
            )
        return n
    finally:
        conn.close()


def run_all() -> None:
    total = 0
    for name in TASKS:
        try:
            total += run_task(name)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[{name}] task failed: {e} (other tasks continue)")
    logger.info(f"=== all tasks done, {total} rows written/updated ===")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: python -m greenchain.main <task_name>\navailable: {list(TASKS)} or 'all'")
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "all":
        run_all()
    else:
        run_task(arg)
