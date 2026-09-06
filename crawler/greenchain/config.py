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
    "1519",  # Hua Eng Wire & Cable   - grid transformers
    "1513",  # Chung-Hsin Electric    - switchgear / EV charging stations
    "1503",  # Shihlin Electric       - motors / traction / switchgear
    "2201",  # Yulon Motor            - passenger EV assembly
    "2206",  # Sanyang Motor (SYM)    - electric scooters / EV
    "1723",  # China Steel Chemical   - battery anode / carbon materials
    "4739",  # Cupric Technology      - cathode precursors / battery recycling
    "5227",  # Aleees (Advanced Lithium Electrochemistry) - LFP cathode material
    "3576",  # United Renewable Energy - solar cells & modules
    "6244",  # Motech Industries      - solar cells & modules
    "3708",  # Swancor Holding        - wind-blade resin / composites
]
