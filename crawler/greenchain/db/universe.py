"""
Single source of truth for "which companies do we track".

The list is read from the `supply_chain_company` table so that adding or
removing a name is a one-line CSV edit + reseed, not a code change. If that
table is empty or missing (cold database, first run before seed), we fall back
to the constant in config.py so the crawler still has work to do.
"""
from typing import List
from loguru import logger

from ..config import FALLBACK_STOCK_IDS


def load_stock_ids(conn) -> List[str]:
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT StockID FROM supply_chain_company ORDER BY StockID")
            ids = [str(r["StockID"]).strip() for r in cursor.fetchall()]
        if ids:
            return ids
        logger.info("[universe] supply_chain_company is empty; using fallback list from config")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[universe] could not read supply_chain_company ({e}); using fallback list")
    return list(FALLBACK_STOCK_IDS)
