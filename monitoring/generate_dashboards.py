"""
Generate the Grafana dashboard JSON programmatically instead of hand-editing a
big blob of JSON. Keeping gridPos, panel ids and target structure in code means
they cannot drift out of sync, and adding a panel later is one helper call.

Run:    python generate_dashboards.py
Output: grafana/dashboards/*.json
"""
import json
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grafana", "dashboards")
os.makedirs(OUT_DIR, exist_ok=True)

MYSQL_UID = "mysql-greenchain"
PROM_UID = "prometheus"


def panel(id_, title, gridPos, type_, targets, datasource_uid, extra=None):
    p = {
        "id": id_,
        "title": title,
        "type": type_,
        "gridPos": gridPos,
        "datasource": {
            "type": "mysql" if datasource_uid == MYSQL_UID else "prometheus",
            "uid": datasource_uid,
        },
        "targets": targets,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
    }
    if extra:
        p.update(extra)
    return p


def mysql_target(raw_sql, fmt="time_series", ref="A"):
    return {
        "refId": ref,
        "datasource": {"type": "mysql", "uid": MYSQL_UID},
        "rawSql": raw_sql,
        "format": fmt,
        "rawQuery": True,
    }


def promql_target(expr, legend=None, ref="A"):
    t = {"refId": ref, "datasource": {"type": "prometheus", "uid": PROM_UID}, "expr": expr}
    if legend:
        t["legendFormat"] = legend
    return t


def dashboard(uid, title, panels, tags):
    return {
        "uid": uid,
        "title": title,
        "tags": tags,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "1m",
        "time": {"from": "now-1y", "to": "now"},
        "panels": panels,
    }


# ---------------------------------------------------------------------------
# Business dashboard (MySQL datasource) - the supply-chain analytics view
# ---------------------------------------------------------------------------
LATEST_MONTH = "(SELECT MAX(Month) FROM monthly_revenue)"

business_panels = [
    panel(1, "Companies tracked", {"x": 0, "y": 0, "w": 5, "h": 4}, "stat",
          [mysql_target("SELECT COUNT(*) AS value FROM supply_chain_company", "table")],
          MYSQL_UID),

    panel(2, "Sub-sectors", {"x": 5, "y": 0, "w": 5, "h": 4}, "stat",
          [mysql_target("SELECT COUNT(DISTINCT SubSector) AS value FROM supply_chain_company", "table")],
          MYSQL_UID),

    panel(3, "Latest revenue month in DB", {"x": 10, "y": 0, "w": 6, "h": 4}, "table",
          [mysql_target("SELECT MAX(Month) AS `Latest month` FROM monthly_revenue", "table")],
          MYSQL_UID),

    panel(4, "Basket avg return, ~60 trading rows", {"x": 16, "y": 0, "w": 8, "h": 4}, "stat",
          [mysql_target(
              "WITH ranked AS (SELECT StockID, Close, "
              "ROW_NUMBER() OVER (PARTITION BY StockID ORDER BY Date DESC) rn FROM stock_price "
              "WHERE Close IS NOT NULL) "
              "SELECT ROUND(AVG((a.Close/b.Close-1)*100),2) AS value "
              "FROM (SELECT StockID, Close FROM ranked WHERE rn=1) a "
              "JOIN (SELECT StockID, Close FROM ranked WHERE rn=60) b ON a.StockID=b.StockID", "table")],
          MYSQL_UID,
          extra={"fieldConfig": {"defaults": {"unit": "percent", "decimals": 1}, "overrides": []}}),

    panel(5, "Latest-month revenue by sub-sector (thousand NTD)", {"x": 0, "y": 4, "w": 12, "h": 9}, "barchart",
          [mysql_target(
              "SELECT c.SubSector AS metric, SUM(r.RevenueThousandNTD) AS value "
              "FROM monthly_revenue r JOIN supply_chain_company c ON r.StockID=c.StockID "
              f"WHERE r.Month={LATEST_MONTH} GROUP BY c.SubSector ORDER BY value DESC", "table")],
          MYSQL_UID),

    panel(6, "Sub-sector revenue-weighted YoY % (momentum)", {"x": 12, "y": 4, "w": 12, "h": 9}, "timeseries",
          [mysql_target(
              "SELECT STR_TO_DATE(CONCAT(r.Month,'-01'),'%Y-%m-%d') AS time, c.SubSector AS metric, "
              "SUM(r.RevenueThousandNTD*r.YoYPct)/NULLIF(SUM(r.RevenueThousandNTD),0) AS value "
              "FROM monthly_revenue r JOIN supply_chain_company c ON r.StockID=c.StockID "
              "WHERE r.YoYPct IS NOT NULL GROUP BY r.Month, c.SubSector ORDER BY time", "time_series")],
          MYSQL_UID),

    panel(7, "Share price rebased to 100 (per company)", {"x": 0, "y": 13, "w": 12, "h": 9}, "timeseries",
          [mysql_target(
              "SELECT p.Date AS time, c.CompanyName AS metric, "
              "p.Close / FIRST_VALUE(p.Close) OVER (PARTITION BY p.StockID ORDER BY p.Date) * 100 AS value "
              "FROM stock_price p JOIN supply_chain_company c ON p.StockID=c.StockID "
              "WHERE p.Close IS NOT NULL ORDER BY time", "time_series")],
          MYSQL_UID),

    panel(8, "Operating margin % by company (quarterly)", {"x": 12, "y": 13, "w": 12, "h": 9}, "timeseries",
          [mysql_target(
              "SELECT STR_TO_DATE(CONCAT(q.Year,'-',(q.Quarter-1)*3+1,'-01'),'%Y-%m-%d') AS time, "
              "c.CompanyName AS metric, q.OperatingMarginPct AS value "
              "FROM quarterly_margins q JOIN supply_chain_company c ON q.StockID=c.StockID ORDER BY time", "time_series")],
          MYSQL_UID),

    panel(9, "Trailing return leaderboard (60 trading rows)", {"x": 0, "y": 22, "w": 12, "h": 9}, "table",
          [mysql_target(
              "WITH ranked AS (SELECT StockID, Close, "
              "ROW_NUMBER() OVER (PARTITION BY StockID ORDER BY Date DESC) rn FROM stock_price "
              "WHERE Close IS NOT NULL) "
              "SELECT c.CompanyName AS `Company`, c.SubSector AS `Sub-sector`, "
              "ROUND((a.Close/b.Close-1)*100,2) AS `Return %` "
              "FROM (SELECT StockID, Close FROM ranked WHERE rn=1) a "
              "JOIN (SELECT StockID, Close FROM ranked WHERE rn=60) b ON a.StockID=b.StockID "
              "JOIN supply_chain_company c ON a.StockID=c.StockID ORDER BY `Return %` DESC", "table")],
          MYSQL_UID),

    panel(10, "Three-institution net buy, shares (per company)", {"x": 12, "y": 22, "w": 12, "h": 9}, "timeseries",
          [mysql_target(
              "SELECT i.Date AS time, c.CompanyName AS metric, i.ThreeInstitutionNet AS value "
              "FROM institutional_investor i JOIN supply_chain_company c ON i.StockID=c.StockID "
              "ORDER BY time", "time_series")],
          MYSQL_UID),

    panel(11, "Taiwan energy-transition targets (ILLUSTRATIVE - verify each SourceURL)",
          {"x": 0, "y": 31, "w": 24, "h": 8}, "table",
          [mysql_target(
              "SELECT Year, MetricLabel AS `Metric`, TargetValue AS `Target`, ActualValue AS `Actual`, "
              "Unit, Note, SourceURL AS `Source` FROM green_energy_targets ORDER BY Year, Metric", "table")],
          MYSQL_UID),
]

business = dashboard("greenchain-business", "EV & Green-Energy Supply-Chain Analytics",
                     business_panels, ["green-energy", "ev", "business"])

# ---------------------------------------------------------------------------
# Ops dashboard (Prometheus datasource) - observability of the platform itself
# ---------------------------------------------------------------------------
ops_panels = [
    panel(1, "API request rate (req/s)", {"x": 0, "y": 0, "w": 12, "h": 8}, "timeseries",
          [promql_target('sum(rate(http_requests_total{job="greenchain-api"}[5m])) by (handler)', "{{handler}}")],
          PROM_UID),

    panel(2, "API latency p95 (s)", {"x": 12, "y": 0, "w": 12, "h": 8}, "timeseries",
          [promql_target(
              'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="greenchain-api"}[5m])) by (le, handler))',
              "{{handler}}")],
          PROM_UID),

    panel(3, "Mean DB query time by table", {"x": 0, "y": 8, "w": 12, "h": 8}, "timeseries",
          [promql_target(
              'rate(greenchain_api_db_query_duration_seconds_sum[5m]) / rate(greenchain_api_db_query_duration_seconds_count[5m])',
              "{{table_name}}")],
          PROM_UID),

    panel(4, "Active DB connections", {"x": 12, "y": 8, "w": 6, "h": 8}, "stat",
          [promql_target("greenchain_api_active_db_connections")],
          PROM_UID),

    panel(5, "Cumulative DB errors", {"x": 18, "y": 8, "w": 6, "h": 8}, "stat",
          [promql_target("sum(greenchain_api_db_errors_total)")],
          PROM_UID,
          extra={"fieldConfig": {"defaults": {"thresholds": {"mode": "absolute",
                                                             "steps": [{"color": "green", "value": None},
                                                                       {"color": "red", "value": 1}]}}, "overrides": []}}),
]

ops = dashboard("greenchain-ops", "Platform System Monitoring", ops_panels, ["green-energy", "ops"])

for d in (business, ops):
    path = os.path.join(OUT_DIR, f"{d['uid']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"wrote {path}")
