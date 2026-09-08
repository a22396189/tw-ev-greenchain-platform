"""
Configuration for the ingestion package.

Everything is read from environment variables. Running locally (SQLite-free
tests, or `python -m greenchain.*` directly) falls back to the defaults below;
inside the containers the values are overridden by the `environment` block in
docker-compose.yml.
"""
import os

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "greenchain_test_pw")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "greenchain_market")

REQUEST_TIMEOUT = 10

# Fallback stock universe: Taiwan EV & green-energy supply-chain names.
# The authoritative list lives in the `supply_chain_company` table (seeded from
# data_seed/supply_chain_company.csv). This constant is only used when that table
# is empty or unreachable, so the crawler still has something to do on a cold DB.
FALLBACK_STOCK_IDS = [
    "2308",  # Delta Electronics      - power electronics / EV powertrain
    "6282",  # AcBel Polytech         - power supplies / EV charging
    "1504",  # TECO Electric          - EV traction motors / drives / wind generators
    "1519",  # Fortune Electric       - power transformers / switchgear
    "1513",  # Chung-Hsin Electric    - switchgear / offshore-wind substations
    "1503",  # Shihlin Electric       - switchgear / renewable inverters
    "1609",  # Ta Ya Electric         - power cable / solar IPP
    "9958",  # Century Iron & Steel   - offshore-wind foundations
    "2201",  # Yulon Motor            - passenger EV assembly
    "2206",  # Sanyang Motor (SYM)    - electric scooters / EV
    "2204",  # China Motor            - commercial EV assembly
    "1723",  # China Steel Chemical   - battery anode / carbon materials
    "4739",  # Coremax Corporation    - cathode precursors / battery recycling
]
