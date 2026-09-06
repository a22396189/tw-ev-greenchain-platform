"""
Daily share price for every company in the universe.
Source: Taiwan Stock Exchange STOCK_DAY endpoint
https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMMDD&stockNo=NNNN

Endpoint behaviour: pass any single day inside a month and it returns the whole
month of daily OHLC for that one stock. So to backfill a date range you hit it
once per month per stock, not once per day. We only ever ask for the specific
tickers we care about, which keeps request volume low.
"""
import time
from datetime import date
from typing import Dict, List

import requests
from loguru import logger

from ..config import REQUEST_TIMEOUT

URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.twse.com.tw/zh/page/trading/exchange/STOCK_DAY.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def _roc_date_to_iso(roc_date: str) -> str:
    """'115/08/01' -> '2026-08-01'"""
    y, m, d = roc_date.split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def _clean_number(s):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "--", "---", "X"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_month(year_month: str, stock_id: str) -> List[Dict]:
    """
    One month of daily prices for one stock. `year_month` is 'YYYY-MM'.
    A month with no data (future month, not yet traded) returns [] rather than
    raising.
    """
    yyyymmdd = year_month.replace("-", "") + "01"
    params = {"response": "json", "date": yyyymmdd, "stockNo": stock_id}

    time.sleep(2)  # be polite to TWSE; avoid bursts that look like abuse
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("stat") != "OK" or not payload.get("data"):
        logger.info(f"[stock_price] {stock_id} {year_month}: no data (stat={payload.get('stat')})")
        return []

    fields = payload["fields"]  # 日期 成交股數 成交金額 開盤價 最高價 最低價 收盤價 漲跌價差 成交筆數
    idx = {name: i for i, name in enumerate(fields)}

    rows: List[Dict] = []
    for raw in payload["data"]:
        try:
            rows.append({
                "StockID": stock_id,
                "Date": _roc_date_to_iso(raw[idx["日期"]]),
                "Open": _clean_number(raw[idx["開盤價"]]),
                "High": _clean_number(raw[idx["最高價"]]),
                "Low": _clean_number(raw[idx["最低價"]]),
                "Close": _clean_number(raw[idx["收盤價"]]),
                "Change": _clean_number(raw[idx["漲跌價差"]]),
                "TradeVolume": _clean_number(raw[idx["成交股數"]]),
                "TransactionCount": _clean_number(raw[idx["成交筆數"]]),
                "TradeValue": _clean_number(raw[idx["成交金額"]]),
            })
        except (KeyError, IndexError, ValueError) as e:
            logger.warning(f"[stock_price] skipped an unparseable row: {e} ({raw})")
            continue

    return rows


def fetch_range(stock_ids: List[str], start_month: str, end_month: str) -> List[Dict]:
    """Every month from start_month to end_month (inclusive) for every stock. Used for backfill."""
    y0, m0 = map(int, start_month.split("-"))
    y1, m1 = map(int, end_month.split("-"))

    all_rows: List[Dict] = []
    for stock_id in stock_ids:
        y, m = y0, m0
        while (y, m) <= (y1, m1):
            ym = f"{y:04d}-{m:02d}"
            try:
                all_rows.extend(fetch_month(ym, stock_id))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[stock_price] {stock_id} {ym} failed: {e}; skipping that month")
            m += 1
            if m > 12:
                m = 1
                y += 1
    return all_rows


def fetch_latest(stock_ids: List[str]) -> List[Dict]:
    """
    Current month for every stock (the Airflow daily task). A connection failure
    for one stock is logged and skipped; it never aborts the whole run.
    """
    today = date.today()
    ym = f"{today.year:04d}-{today.month:02d}"
    rows: List[Dict] = []
    for stock_id in stock_ids:
        try:
            rows.extend(fetch_month(ym, stock_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[stock_price] {stock_id}: TWSE request failed ({e}); "
                f"keeping existing DB rows for this stock."
            )
    return rows
