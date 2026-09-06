"""
Quarterly margins (gross / operating / net) for the universe.
Source: TWSE OpenAPI "profitability analysis"
https://openapi.twse.com.tw/v1/opendata/t187ap17_L

This endpoint returns only the latest quarter, for every listed company at once.
So:
  - historical quarters come from data_seed/quarterly_margins_seed.csv (one-time
    load, each row carries a Source note)
  - every run then pulls the latest quarter and upserts it, so the DB always
    holds "seed history + newest live quarter"

One request covers the whole basket - we filter for our tickers in one pass.

Company codes are compared as stripped strings (not ==) because the OpenAPI
payload is inconsistent about number-vs-string and stray whitespace.
"""
from datetime import datetime
from typing import Dict, List

import requests
from loguru import logger

from ..config import REQUEST_TIMEOUT

ENDPOINT = "https://openapi.twse.com.tw/v1/opendata/t187ap17_L"


def fetch_latest(stock_ids: List[str]) -> List[Dict]:
    try:
        resp = requests.get(ENDPOINT, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[quarterly_margins] TWSE OpenAPI failed ({e}); keeping existing DB rows.")
        return []

    wanted = {str(s).strip() for s in stock_ids}
    by_code = {
        str(r.get("公司代號")).strip(): r
        for r in data
        if r.get("公司代號") is not None
    }
    sanity = "2330" in by_code  # TSMC should always be present in a complete payload

    out: List[Dict] = []
    for code in sorted(wanted):
        row = by_code.get(code)
        if row is None:
            logger.info(
                f"[quarterly_margins] {code} not in latest payload "
                f"({'this company is just missing this quarter' if sanity else 'payload looks incomplete'})"
            )
            continue
        try:
            gross = float(row["毛利率(%)(營業毛利)/(營業收入)"])
            operating = float(row["營業利益率(%)(營業利益)/(營業收入)"])
            net_raw = (
                row.get("稅後純益率(%)(稅後純益)/(營業收入)")
                or row.get("稅前純益率(%)(稅前純益)/(營業收入)")
            )
            net = float(net_raw)
            year_roc = int(row.get("年度", 0))
            season = int(row.get("季別", 0))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[quarterly_margins] {code}: field parse failed ({e}); skipping")
            continue

        if not year_roc or not season:
            logger.warning(f"[quarterly_margins] {code}: missing year/quarter; skipping")
            continue

        out.append({
            "StockID": code,
            "Year": year_roc + 1911,
            "Quarter": season,
            "GrossMarginPct": gross,
            "OperatingMarginPct": operating,
            "NetMarginPct": net,
            "Source": "twse_openapi_t187ap17_L",
            "RetrievedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    if out:
        q = f"{out[0]['Year']}Q{out[0]['Quarter']}"
        logger.info(f"[OK][quarterly_margins] live latest quarter {q} for {len(out)} companies")
    return out
