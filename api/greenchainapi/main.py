"""
API layer (FastAPI) for the TW EV & Green-Energy supply-chain platform.

Reads MySQL directly and exposes Prometheus metrics. The "connect -> query ->
time -> rows-to-dicts -> close" logic that every endpoint needs is factored into
one helper (`query`) instead of being copy-pasted per endpoint - same monitoring
coverage, far less code.

Two of the endpoints are not plain table pass-throughs:
  - /sector_revenue_momentum : rolls monthly revenue up by supply-chain sub-sector
  - /relative_strength       : ranks each name's trailing return against the basket
"""
import statistics
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

import pymysql
from fastapi import FastAPI, HTTPException, Query
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

from .config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

app = FastAPI(title="TW EV & Green-Energy Supply-Chain Analytics API", version="1.0.0")

Instrumentator().instrument(app).expose(app)

api_queries_counter = Counter(
    "greenchain_api_queries_total", "total API queries", ["endpoint"]
)
db_query_duration = Histogram(
    "greenchain_api_db_query_duration_seconds", "DB query duration", ["table_name"]
)
db_errors_counter = Counter(
    "greenchain_api_db_errors_total", "total DB errors", ["endpoint", "error_type"]
)
active_db_connections = Gauge(
    "greenchain_api_active_db_connections", "DB connections currently in use"
)


def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor,
    )


def query(endpoint: str, table: str, sql: str, params: tuple) -> List[Dict]:
    """Shared query path: count calls, time the query, count errors, track live connections."""
    api_queries_counter.labels(endpoint=endpoint).inc()
    conn = None
    try:
        conn = get_conn()
        active_db_connections.inc()
        with conn.cursor() as cursor:
            t0 = time.time()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            db_query_duration.labels(table_name=table).observe(time.time() - t0)
        for r in rows:
            for k, v in r.items():
                if isinstance(v, date):
                    r[k] = v.isoformat()
        return rows
    except pymysql.Error as e:
        db_errors_counter.labels(endpoint=endpoint, error_type=type(e).__name__).inc()
        raise HTTPException(status_code=500, detail=f"database query error: {e}")
    finally:
        if conn is not None:
            conn.close()
            active_db_connections.dec()


@app.get("/")
def read_root():
    return {
        "service": "TW EV & Green-Energy Supply-Chain Analytics",
        "docs": "/docs",
        "metrics": "/metrics",
    }


@app.get("/companies")
def companies() -> Dict[str, List[Dict]]:
    """The analysed universe: ticker, sub-sector, supply-chain tier, product focus."""
    sql = "SELECT * FROM supply_chain_company ORDER BY SubSector, ChainTier, StockID"
    return {"data": query("companies", "supply_chain_company", sql, ())}


@app.get("/stock_price")
def stock_price(
    stock_id: str = Query("2308"),
    start_date: str = Query("1900-01-01"),
    end_date: str = Query("2999-12-31"),
) -> Dict[str, List[Dict]]:
    sql = (
        "SELECT * FROM stock_price WHERE StockID=%s AND `Date` BETWEEN %s AND %s "
        "ORDER BY `Date`"
    )
    return {"data": query("stock_price", "stock_price", sql, (stock_id, start_date, end_date))}


@app.get("/institutional_investor")
def institutional_investor(
    stock_id: str = Query("2308"),
    start_date: str = Query("1900-01-01"),
    end_date: str = Query("2999-12-31"),
) -> Dict[str, List[Dict]]:
    sql = (
        "SELECT * FROM institutional_investor WHERE StockID=%s AND `Date` BETWEEN %s AND %s "
        "ORDER BY `Date`"
    )
    return {
        "data": query(
            "institutional_investor", "institutional_investor", sql,
            (stock_id, start_date, end_date),
        )
    }


@app.get("/quarterly_margins")
def quarterly_margins(stock_id: Optional[str] = Query(None)) -> Dict[str, List[Dict]]:
    if stock_id:
        sql = "SELECT * FROM quarterly_margins WHERE StockID=%s ORDER BY Year, Quarter"
        return {"data": query("quarterly_margins", "quarterly_margins", sql, (stock_id,))}
    sql = "SELECT * FROM quarterly_margins ORDER BY StockID, Year, Quarter"
    return {"data": query("quarterly_margins", "quarterly_margins", sql, ())}


@app.get("/monthly_revenue")
def monthly_revenue(stock_id: Optional[str] = Query(None)) -> Dict[str, List[Dict]]:
    if stock_id:
        sql = "SELECT * FROM monthly_revenue WHERE StockID=%s ORDER BY Month"
        return {"data": query("monthly_revenue", "monthly_revenue", sql, (stock_id,))}
    sql = "SELECT * FROM monthly_revenue ORDER BY StockID, Month"
    return {"data": query("monthly_revenue", "monthly_revenue", sql, ())}


@app.get("/green_energy_targets")
def green_energy_targets() -> Dict[str, List[Dict]]:
    """Curated national energy-transition targets vs actuals (Bureau of Energy / NDC; SourceURL per row)."""
    sql = "SELECT * FROM green_energy_targets ORDER BY Year, Metric"
    return {"data": query("green_energy_targets", "green_energy_targets", sql, ())}


@app.get("/sector_revenue_momentum")
def sector_revenue_momentum() -> Dict:
    """
    Insight endpoint (not a table pass-through).

    Joins monthly_revenue to the supply-chain dimension, then for the most recent
    month that at least half the universe has reported, aggregates by sub-sector:
      - total revenue (thousand NTD)
      - revenue-weighted average YoY %
      - MoM change vs the previous month
      - company count

    Sub-sectors are ranked by weighted YoY, so the answer to "which part of the
    green-energy chain is accelerating right now" falls straight out.
    """
    sql = """
        SELECT r.Month, r.StockID, r.RevenueThousandNTD, r.YoYPct,
               c.SubSector, c.ChainTier
        FROM monthly_revenue r
        JOIN supply_chain_company c ON r.StockID = c.StockID
        ORDER BY r.Month
    """
    rows = query("sector_revenue_momentum", "monthly_revenue", sql, ())
    if not rows:
        return {"error": "no monthly_revenue rows joined to a known company"}

    months = sorted({r["Month"] for r in rows})
    universe = {r["StockID"] for r in rows}
    min_reporters = max(1, len(universe) // 2)

    def well_covered(mth: str) -> bool:
        return len({r["StockID"] for r in rows if r["Month"] == mth}) >= min_reporters

    # newest month reported by >= half the universe
    latest = next((m for m in reversed(months) if well_covered(m)), months[-1])

    # MoM is only meaningful against the immediately preceding calendar month, and
    # only if that month is itself well covered. A half-reported month (a few early
    # filers) would make every sub-sector's MoM look like +600% / +1,000%.
    y, m = int(latest[:4]), int(latest[5:7])
    prev_cal = f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"
    prev = prev_cal if prev_cal in months and well_covered(prev_cal) else None

    def agg(month):
        buckets: Dict[str, Dict] = {}
        for r in rows:
            if r["Month"] != month or r["RevenueThousandNTD"] is None:
                continue
            b = buckets.setdefault(r["SubSector"], {"rev": 0, "wy": 0.0, "n": 0})
            b["rev"] += r["RevenueThousandNTD"]
            if r["YoYPct"] is not None:
                b["wy"] += r["RevenueThousandNTD"] * float(r["YoYPct"])
            b["n"] += 1
        return buckets

    cur, pre = agg(latest), agg(prev) if prev else {}

    out = []
    for sub, b in cur.items():
        weighted_yoy = round(b["wy"] / b["rev"], 2) if b["rev"] else None
        mom = None
        if sub in pre and pre[sub]["rev"]:
            mom = round((b["rev"] / pre[sub]["rev"] - 1) * 100, 2)
        out.append({
            "sub_sector": sub,
            "companies_reporting": b["n"],
            "total_revenue_thousand_ntd": b["rev"],
            "weighted_yoy_pct": weighted_yoy,
            "mom_pct": mom,
        })
    out.sort(key=lambda x: (x["weighted_yoy_pct"] is None, -(x["weighted_yoy_pct"] or 0)))

    return {
        "as_of_month": latest,
        "compare_prev_month": prev,
        "ranked_by": "weighted_yoy_pct",
        "sectors": out,
    }


@app.get("/relative_strength")
def relative_strength(lookback_days: int = Query(60, ge=5, le=750)) -> Dict:
    """
    Insight endpoint (not a table pass-through).

    For each company, trailing return over `lookback_days` calendar days
    (last close vs the earliest close on/after the window start). Each name's
    excess return is measured against the basket median; sub-sector averages are
    rolled up too. Answers "who is leading / lagging the green-energy basket".
    """
    price_sql = """
        SELECT p.StockID, p.Date, p.Close, c.CompanyName, c.SubSector
        FROM stock_price p
        JOIN supply_chain_company c ON p.StockID = c.StockID
        WHERE p.Close IS NOT NULL
        ORDER BY p.StockID, p.Date
    """
    rows = query("relative_strength", "stock_price", price_sql, ())
    if not rows:
        return {"error": "no stock_price rows joined to a known company"}

    all_dates = sorted({r["Date"] for r in rows})
    end_date = all_dates[-1]
    window_start = (date.fromisoformat(end_date) - timedelta(days=lookback_days)).isoformat()

    per_stock: Dict[str, List[Dict]] = {}
    for r in rows:
        per_stock.setdefault(r["StockID"], []).append(r)

    results = []
    for sid, series in per_stock.items():
        in_window = [s for s in series if s["Date"] >= window_start]
        if len(in_window) < 2:
            continue
        start_close = float(in_window[0]["Close"])
        end_close = float(in_window[-1]["Close"])
        if start_close <= 0:
            continue
        ret = (end_close / start_close - 1) * 100
        results.append({
            "stock_id": sid,
            "company": series[0]["CompanyName"],
            "sub_sector": series[0]["SubSector"],
            "return_pct": round(ret, 2),
            "from_date": in_window[0]["Date"],
            "to_date": in_window[-1]["Date"],
        })

    if not results:
        return {"error": f"not enough price history within the last {lookback_days} days"}

    median_ret = statistics.median(r["return_pct"] for r in results)
    for r in results:
        r["excess_vs_median_pct"] = round(r["return_pct"] - median_ret, 2)
    results.sort(key=lambda x: -x["return_pct"])

    sector_roll: Dict[str, List[float]] = {}
    for r in results:
        sector_roll.setdefault(r["sub_sector"], []).append(r["return_pct"])
    sectors = sorted(
        ({"sub_sector": s, "avg_return_pct": round(statistics.mean(v), 2), "companies": len(v)}
         for s, v in sector_roll.items()),
        key=lambda x: -x["avg_return_pct"],
    )

    return {
        "lookback_days": lookback_days,
        "window": {"from": window_start, "to": end_date},
        "basket_median_return_pct": round(median_ret, 2),
        "leaders": results[:3],
        "laggards": results[-3:],
        "all": results,
        "by_sub_sector": sectors,
    }
