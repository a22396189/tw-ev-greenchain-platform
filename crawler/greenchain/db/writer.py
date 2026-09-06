"""
Generic upsert: INSERT ... ON DUPLICATE KEY UPDATE.

Why upsert instead of a plain INSERT: an Airflow DAG can run the same day's
task more than once (re-run, backfill, manual trigger). Upsert makes repeated
execution safe - it never raises on a duplicate key and never creates duplicate
rows. Idempotency is a core property of a data pipeline.
"""
from typing import Any, Dict, List
from loguru import logger


def upsert(conn, table: str, records: List[Dict[str, Any]]) -> int:
    """
    Write a batch of dict rows to MySQL; on a primary-key clash, update the
    non-key columns. Returns the number of rows written/updated. An empty list
    returns 0 without touching the database.
    """
    if not records:
        return 0

    columns = list(records[0].keys())
    col_list = ", ".join(f"`{c}`" for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_clause = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in columns)

    sql = (
        f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    rows = [tuple(r.get(c) for c in columns) for r in records]

    try:
        with conn.cursor() as cursor:
            cursor.executemany(sql, rows)
        conn.commit()
        logger.info(f"[write] {table}: {len(rows)} rows (inserted or updated)")
        return len(rows)
    except Exception as e:
        conn.rollback()
        logger.error(f"[write failed] {table}: {e}")
        raise
