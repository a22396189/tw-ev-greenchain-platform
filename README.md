# Taiwan EV & Green-Energy Supply-Chain Analytics Platform

A containerised data platform that tracks a **basket of Taiwan-listed EV and
green-energy supply-chain companies** — share price, institutional flows,
quarterly margins, and monthly revenue — and turns the raw feeds into
supply-chain-level insight: which tier of the chain has revenue momentum right
now, and which names are leading or lagging the basket.

The stack is the classic batch-analytics pattern:

```
Airflow (schedule) -> Python crawler -> MySQL -> FastAPI -> Prometheus / Grafana
```

It is built with Docker Compose so the whole thing comes up with one command.

---

## What it analyses

The tracked universe is defined in
[`data_seed/supply_chain_company.csv`](data_seed/supply_chain_company.csv) —
edit that file (then re-seed) to add or drop names. The default basket, grouped
by sub-sector and supply-chain tier:

| Sub-sector | Companies (default) |
|---|---|
| Power Electronics & Powertrain | Delta Electronics (2308), AcBel Polytech (6282), TECO (1504) |
| Grid & Renewables Infrastructure | Fortune Electric (1519), Chung-Hsin Electric (1513), Shihlin Electric (1503), Ta Ya (1609), Century Iron & Steel (9958) |
| EV Assembly | Yulon Motor (2201), Sanyang Motor / SYM (2206), China Motor (2204) |
| Battery Materials | China Steel Chemical (1723), Coremax (4739) |

Company English names and the sub-sector / tier classification are **editable
metadata** in the seed CSV — adjust them to taste.

Every name in the default basket is **TWSE-listed** so that all four TWSE feeds
(price, institutional, margins, revenue) resolve for it. Solar-cell
manufacturers (URE 3576, Motech 6244) and distressed / TPEx-listed names were
deliberately left out: they are either structurally loss-making, thinly traded,
or invisible to the TWSE endpoints — the same "don't ingest a source you can't
stand behind" judgement that keeps `green_energy_targets` a curated table.

---

## Data tables and sources

| Table | Contents | Source | Update path |
|---|---|---|---|
| `supply_chain_company` | The tracked universe (ticker, sub-sector, chain tier, product focus) | Curated CSV | Pure seed — edit the CSV, re-run seed |
| `stock_price` | Daily OHLC for every company | TWSE `STOCK_DAY` | Seed backfills ~12 months (`STOCK_PRICE_BACKFILL_MONTHS` env var); Airflow adds daily increments |
| `institutional_investor` | Daily foreign / trust / dealer net buy per company | TWSE `T86` | Seed backfills ~30 days; Airflow re-pulls a rolling 7-day window each run (missed days self-heal) |
| `quarterly_margins` | Gross / operating / net margin per company per quarter | History: FinMind `TaiwanStockFinancialStatements` (real, in seed CSV). Live: TWSE OpenAPI `t187ap17_L` | Seed loads real history; Airflow upserts the latest quarter each run |
| `monthly_revenue` | Monthly revenue + YoY per company | History: FinMind `TaiwanStockMonthRevenue` (real, in seed CSV). Live: TWSE OpenAPI `t187ap05_L` | Same pattern as margins |
| `green_energy_targets` | National energy-transition targets vs actuals (solar / offshore wind / renewable share / BEV sales share / net zero) | Bureau of Energy, NDC 2050 net-zero roadmap, press (per-row `SourceURL`), as of 2026-09 | Pure seed; hand-curated from the sources above |

### Why margin / revenue history comes from a seed CSV

The live TWSE feeds `t187ap17_L` and `t187ap05_L` return **only the newest
period** (latest quarter / latest month), for every listed company at once —
there is no historical range query. So the platform loads a real history
baseline from `data_seed/quarterly_margins_seed.csv` and
`data_seed/monthly_revenue_seed.csv` (pulled from FinMind on 2026-09-08; margins
are computed as GrossProfit / OperatingIncome / IncomeAfterTaxes over quarterly
Revenue), and then on every run pulls the newest period from TWSE and upserts
it. One live request covers the whole basket — the crawler filters out the
tickers it cares about in a single pass.

To refresh the history, re-pull from FinMind and rewrite the two seed CSVs, or
just let the live feed accumulate new periods month by month.

### Why `green_energy_targets` is a hand-curated table, not a crawl

Taiwan's solar / offshore-wind / renewable-share / net-zero / EV targets are
published as policy statements and periodic statistics bulletins — not a stable
structured API — and the exact numbers get revised between documents. So this
table is **hand-curated** from the Bureau of Energy, the NDC 2050 net-zero
roadmap and reported figures (each row carries a `SourceURL`, pulled 2026-09).
Notable gaps it captures: the 2025 renewable-generation-share goal was 20% and
the actual came in at ~13%; solar reached ~15.5 GW against a 20 GW goal.
Re-check the sources before quoting these — energy statistics move — but the
choice to curate rather than scrape a brittle page is itself a data-governance
decision worth defending.

---

## The two insight endpoints

Most endpoints are straight table reads. Two are not:

- **`GET /sector_revenue_momentum`** — joins `monthly_revenue` to the
  supply-chain dimension, finds the most recent month at least half the universe
  has reported, and aggregates by sub-sector: total revenue, revenue-weighted
  average YoY %, month-on-month change, company count. Sub-sectors are ranked by
  weighted YoY, so "which part of the green-energy chain is accelerating" drops
  straight out.

- **`GET /relative_strength?lookback_days=60`** — trailing return per company
  over the window, each name's excess return versus the **basket median**, plus
  a sub-sector roll-up. Answers "who is leading / lagging the basket".

---

## System architecture

```
                         +-----------------------+
      weekdays 21:00      |   Apache Airflow       |  auto-trigger, or hit
      schedule    ------->|  (webserver+scheduler) |  "Trigger DAG" in the UI
                         +-----------+-----------+
                                     | PythonOperator calls the package directly
                                     v
                         +-----------------------+       live sources:
                         |   greenchain crawler   |<----- TWSE STOCK_DAY   (price)
                         |  (4 independent tasks)  |<----- TWSE T86         (institutions)
                         +-----------+-----------+<----- TWSE OpenAPI     (margins / revenue)
                                     | upsert (idempotent)
                                     v
                         +-----------------------+       one-time load:
                         |       MySQL 8.0        |<----- data_seed/*.csv
                         |   (6 tables)           |     (universe + energy targets)
                         +------+----------+------+
                                |          |
                   +------------v--+   +---v------------------+
                   |  FastAPI (8888)|   | Grafana MySQL        |
                   |  /docs         |   | datasource (business)|
                   +------+---------+   +---------------------+
                          | /metrics
                          v
                   +--------------+    +----------------------+
                   |  Prometheus   |-->| Grafana ops dashboard |
                   +--------------+    +----------------------+
```

### Deliberate engineering choices

| Area | Choice | Why |
|---|---|---|
| Orchestration | Docker **Compose**, one file | One command to start; no Swarm init / overlay network / external volumes to get wrong during a live demo |
| Airflow -> crawler | **PythonOperator** importing the package | Avoids mounting `docker.sock` into Airflow and the docker-in-docker permission problems that plague Windows Docker Desktop; the schedule is unchanged |
| Airflow version | **2.9.3** (stable) | Fewer surprise startup issues than the newest line |
| Airflow layout | Official three-part split: `airflow-init` / `webserver` / `scheduler` | Easier to see which stage failed |
| Grafana data sources | Prometheus **+ MySQL** | The MySQL source is what makes the business dashboard possible — sub-sector momentum, relative strength, margins — not just API QPS |
| Institutional-flow crawl | Pull the whole-market `T86` once per day, filter the basket; daily task re-pulls a rolling 7-day window | One request covers all tickers; the rolling window means a few missed scheduled runs self-heal (upsert makes the repeats free) |
| Universe definition | Single source of truth in `supply_chain_company` | Add a company = one CSV line + re-seed, no code change |
| Basket selection | All-TWSE, exclude structurally loss-making / TPEx names | Every feed resolves for every name; the momentum and margin charts stay readable |

---

## Prerequisites

1. **Docker Desktop** (WSL2 backend on Windows).
   <https://www.docker.com/products/docker-desktop/>
2. At least **~6 GB RAM** available to the Docker engine (MySQL + Airflow +
   Postgres + Prometheus + Grafana + exporters = 7-8 containers). On the WSL2
   backend this is managed by Windows / `%UserProfile%\.wslconfig`, not the
   Docker Desktop Resources sliders; the WSL2 default (≈50% of host RAM) is
   usually plenty.
3. Internet access (the crawler reaches the Taiwan Stock Exchange; Docker needs
   Docker Hub for base images).

---

## First run

**Option A: double-click `start_demo.bat`** (Windows; runs every step below and
opens the browser tabs).

**Option B: manual**

```bash
# 1. build the crawler / api images
docker compose build

# 2. start MySQL and wait for it
docker compose up -d mysql

# 3. create tables + load seed data + backfill history (needs internet, a few minutes)
docker compose run --rm crawler python -m greenchain.seed

# 4. start everything else
docker compose up -d
```

First start pulls Airflow / Postgres / Grafana / Prometheus images and
initialises the Airflow metadata DB — **5-10 minutes is normal**. After that,
`docker compose up -d` brings the stack back in seconds.

To load only the CSVs and skip all network calls (offline test):

```bash
docker compose run --rm -e SEED_SKIP_LIVE_BACKFILL=1 crawler python -m greenchain.seed
```

---

## Service URLs

| Service | URL | Login |
|---|---|---|
| Grafana (main view) | <http://localhost:3000> | admin / admin |
| Airflow (schedule UI) | <http://localhost:8080> | admin / admin |
| FastAPI interactive docs | <http://localhost:8888/docs> | none |
| Prometheus | <http://localhost:9090> | none |
| phpMyAdmin | <http://localhost:8000> | root / `MYSQL_ROOT_PASSWORD` from `.env` |

---

## Demo walk-through

1. **Grafana "EV & Green-Energy Supply-Chain Analytics"** — sub-sector revenue
   momentum, price rebased to 100 per name, operating-margin trends, the
   trailing-return leaderboard, institutional flows.
2. **Airflow** — open `greenchain_data_pipeline`, hit **Trigger DAG**, watch the
   four tasks go green. Proves the schedule is real.
3. **FastAPI `/docs`** — run `/sector_revenue_momentum` and
   `/relative_strength`. These are the endpoints with actual analytical logic,
   not database pass-throughs.
4. **Grafana "Platform System Monitoring"** (optional) — API latency, DB query
   time, connection count: the observability story.

---

## Manual crawler commands

```bash
# one task
docker compose run --rm crawler python -m greenchain.main stock_price
docker compose run --rm crawler python -m greenchain.main monthly_revenue

# all four
docker compose run --rm crawler python -m greenchain.main all

# re-seed after editing data_seed/*.csv
docker compose run --rm crawler python -m greenchain.seed
```

---

## Regenerating the Grafana dashboards

The dashboard JSON is generated, not hand-written:

```bash
cd monitoring
python generate_dashboards.py
```

Output goes to `monitoring/grafana/dashboards/*.json`, which Grafana
auto-provisions on start.

---

## Troubleshooting

- **`docker compose build` hangs / fails** — check the network; Docker needs
  Docker Hub for base images.
- **Grafana dashboard is empty** — confirm
  `docker compose run --rm crawler python -m greenchain.seed` finished without
  errors; check the tables in phpMyAdmin.
- **Airflow web UI won't open** — it is the slowest container; wait 1-2 minutes
  after `docker compose up -d` and refresh.
- **Port already in use (3000 / 8080 / ...)** — change the `ports` mapping in
  `docker-compose.yml`, e.g. `"3001:3000"`, then use the new port.
- **`[warn] ... TWSE request failed`** — the crawler could not reach the
  exchange this run; it skips the update and keeps the existing DB rows rather
  than crashing. This is intentional fault tolerance, not a bug.

---

## Data-quality notes

- `quarterly_margins_seed.csv` and `monthly_revenue_seed.csv` contain **real
  data** pulled from FinMind on 2026-09-08 (`Source` column names the dataset).
  Margins are derived as GrossProfit / OperatingIncome / IncomeAfterTaxes over
  single-quarter Revenue; a few quarters carry large non-operating swings (asset
  disposals, investment income) that are real but move the net-margin line —
  read them alongside the operating-margin line.
- The share-price and institutional-flow feeds are real TWSE endpoints; the seed
  backfills them directly (no CSV).
- `green_energy_targets` is hand-curated from the Bureau of Energy / NDC (pulled
  2026-09; each row carries a `SourceURL`). Energy statistics get revised, so
  re-check the sources before quoting — but the figures reflect real published
  targets and actuals, not placeholders.

## Testing status

The pipeline logic, the FastAPI service (both insight endpoints exercised with
stubbed data), the Compose file syntax, the seed CSVs against the schema, and
the generated dashboard JSON have been checked locally. A full `docker compose
up` across all containers, and the live TWSE crawlers under real network
conditions, should be verified on the target machine before any live demo.
