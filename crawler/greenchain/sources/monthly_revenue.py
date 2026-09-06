"""
Monthly revenue for the universe.
Source: TWSE OpenAPI "monthly operating revenue"
https://openapi.twse.com.tw/v1/opendata/t187ap05_L

Same pattern as quarterly_margins: the endpoint returns only the latest month
for all listed companies at once. Historical months come from
data_seed/monthly_revenue_seed.csv; every run pulls the newest month and
upserts it. One request covers the whole basket.
"""
from datetime import datetime
from typing import Dict, List

import requests
from loguru import logger

from ..config import REQUEST_TIMEOUT

ENDPOINT = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"


def fetch_latest(stock_ids: List[str]) -> List[Dict]:
    try:
        resp = requests.get(ENDPOINT, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[monthly_revenue] TWSE OpenAPI failed ({e}); keeping existing DB rows.")
        return []

    wanted = {str(s).strip() for s in stock_ids}
    by_code = {
        str(r.get("公司代號")).strip(): r
        for r in data
        if r.get("公司代號") is not None
    }
    sanity = "2330" in by_code

    out: List[Dict] = []
    for code in sorted(wanted):
        row = by_code.get(code)
        if row is None:
            logger.info(
                f"[monthly_revenue] {code} not in latest payload "
                f"({'company missing this month' if sanity else 'payload looks incomplete'})"
            )
            continue
        try:
            data_ym = str(row.get("資料年月", "")).strip()  # e.g. "11507" = ROC 115 / month 07
            if len(data_ym) != 5:
                raise ValueError(f"unexpected 資料年月: {data_ym!r}")
            year_roc, month = int(data_ym[:3]), int(data_ym[3:])
            revenue = int(float(row["營業收入-當月營收"]))
            yoy_raw = row.get("營業收入-去年同月增減(%)")
            yoy = float(yoy_raw) if yoy_raw not in (None, "") else None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[monthly_revenue] {code}: field parse failed ({e}); skipping")
            continue

        out.append({
            "StockID": code,
            "Month": f"{year_roc + 1911:04d}-{month:02d}",
            "RevenueThousandNTD": revenue,
            "YoYPct": yoy,
            "Source": "twse_openapi_t187ap05_L",
            "RetrievedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    if out:
        logger.info(f"[OK][monthly_revenue] live latest month {out[0]['Month']} for {len(out)} companies")
    return out
