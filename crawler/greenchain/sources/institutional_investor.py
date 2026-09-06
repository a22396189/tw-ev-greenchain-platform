"""
Daily foreign / investment-trust / dealer net buy for the universe.
Source: TWSE "three primary institutional investors" table
https://www.twse.com.tw/fund/T86?date=YYYYMMDD&selectType=ALLBUT0999&response=json

Endpoint behaviour: one request returns the whole market for that day. There is
no per-stock query, so we pull the day once and filter out every ticker in our
universe in a single pass - the basket costs exactly one request per day.

Backfill is day-by-day (no monthly endpoint like STOCK_DAY has), so it is slow;
keep the backfill window short (e.g. last 30-45 days).
"""
import time
from datetime import date, timedelta
from typing import Dict, List

import requests
from loguru import logger

from ..config import REQUEST_TIMEOUT

URL = "https://www.twse.com.tw/fund/T86"

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.twse.com.tw/zh/page/trading/fund/T86.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def _clean_int(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "--", "---"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def fetch_day(iso_date: str, stock_ids: List[str]) -> List[Dict]:
    """
    Whole-market institutional flows for one day, filtered to `stock_ids`.
    A non-trading day (weekend/holiday, or not yet published) returns [].
    """
    yyyymmdd = iso_date.replace("-", "")
    params = {"date": yyyymmdd, "selectType": "ALLBUT0999", "response": "json"}

    time.sleep(2)
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("stat") != "OK" or not payload.get("data"):
        logger.info(f"[institutional_investor] {iso_date}: no data (non-trading day or not published)")
        return []

    fields = payload["fields"]
    idx = {name: i for i, name in enumerate(fields)}
    wanted = {str(s).strip() for s in stock_ids}

    def col(row, name):
        return _clean_int(row[idx[name]]) if name in idx else None

    out: List[Dict] = []
    for r in payload["data"]:
        code = str(r[idx["證券代號"]]).strip()
        if code not in wanted:
            continue

        foreign_buy = (col(r, "外陸資買進股數(不含外資自營商)") or 0) + (col(r, "外資自營商買進股數") or 0)
        foreign_sell = (col(r, "外陸資賣出股數(不含外資自營商)") or 0) + (col(r, "外資自營商賣出股數") or 0)

        out.append({
            "StockID": code,
            "Date": iso_date,
            "ForeignBuy": foreign_buy,
            "ForeignSell": foreign_sell,
            "ForeignNet": foreign_buy - foreign_sell,
            "InvestmentTrustBuy": col(r, "投信買進股數"),
            "InvestmentTrustSell": col(r, "投信賣出股數"),
            "InvestmentTrustNet": col(r, "投信買賣超股數"),
            "DealerNet": col(r, "自營商買賣超股數"),
            "ThreeInstitutionNet": col(r, "三大法人買賣超股數"),
        })

    missing = wanted - {r["StockID"] for r in out}
    if missing:
        logger.info(f"[institutional_investor] {iso_date}: no rows for {sorted(missing)} (may be normal)")
    return out


def fetch_range(stock_ids: List[str], start_date: str, end_date: str) -> List[Dict]:
    """Day-by-day backfill (weekends skipped automatically)."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    rows: List[Dict] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            try:
                rows.extend(fetch_day(d.isoformat(), stock_ids))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[institutional_investor] {d.isoformat()} failed: {e}; skipping")
        d += timedelta(days=1)
    return rows


def fetch_latest(stock_ids: List[str]) -> List[Dict]:
    """Today's institutional flows for the universe (Airflow daily task)."""
    today = date.today().isoformat()
    try:
        return fetch_day(today, stock_ids)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[institutional_investor] TWSE request failed ({e}); "
            f"keeping existing DB rows."
        )
        return []
