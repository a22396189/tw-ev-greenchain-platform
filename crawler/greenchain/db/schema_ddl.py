"""
Table definitions. Everything is CREATE TABLE IF NOT EXISTS, so the schema is
created automatically the first time the crawler (or any Airflow task) runs -
no separate migration step.

Six tables:
  - stock_price            : daily OHLC per company in the universe
  - institutional_investor : daily foreign / trust / dealer net buy per company
  - quarterly_margins      : quarterly gross / operating / net margin per company
  - monthly_revenue        : monthly revenue + YoY per company
  - supply_chain_company   : dimension table = the analysed universe itself
  - green_energy_targets   : curated national energy-transition targets (no API)
"""

DDL = {
    "supply_chain_company": """
        CREATE TABLE IF NOT EXISTS supply_chain_company (
            StockID      VARCHAR(10)  NOT NULL,
            CompanyName  VARCHAR(80),
            SubSector    VARCHAR(40),
            ChainTier    VARCHAR(20),
            ProductFocus VARCHAR(160),
            ListingBoard VARCHAR(20),
            Note         VARCHAR(255),
            PRIMARY KEY (StockID)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "stock_price": """
        CREATE TABLE IF NOT EXISTS stock_price (
            StockID     VARCHAR(10)   NOT NULL,
            Date        DATE          NOT NULL,
            Open        DECIMAL(10,2),
            High        DECIMAL(10,2),
            Low         DECIMAL(10,2),
            Close       DECIMAL(10,2),
            `Change`    DECIMAL(10,2),
            TradeVolume BIGINT,
            TransactionCount INT,
            TradeValue  BIGINT,
            PRIMARY KEY (StockID, Date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "institutional_investor": """
        CREATE TABLE IF NOT EXISTS institutional_investor (
            StockID             VARCHAR(10) NOT NULL,
            Date                DATE        NOT NULL,
            ForeignBuy          BIGINT,
            ForeignSell         BIGINT,
            ForeignNet          BIGINT,
            InvestmentTrustBuy  BIGINT,
            InvestmentTrustSell BIGINT,
            InvestmentTrustNet  BIGINT,
            DealerNet           BIGINT,
            ThreeInstitutionNet BIGINT,
            PRIMARY KEY (StockID, Date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "quarterly_margins": """
        CREATE TABLE IF NOT EXISTS quarterly_margins (
            StockID    VARCHAR(10) NOT NULL,
            Year       INT         NOT NULL,
            Quarter    INT         NOT NULL,
            GrossMarginPct     DECIMAL(6,2),
            OperatingMarginPct DECIMAL(6,2),
            NetMarginPct       DECIMAL(6,2),
            Source     VARCHAR(64),
            RetrievedAt DATETIME,
            PRIMARY KEY (StockID, Year, Quarter)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "monthly_revenue": """
        CREATE TABLE IF NOT EXISTS monthly_revenue (
            StockID     VARCHAR(10) NOT NULL,
            Month       VARCHAR(7)  NOT NULL,
            RevenueThousandNTD BIGINT,
            YoYPct      DECIMAL(8,2),
            Source      VARCHAR(64),
            RetrievedAt DATETIME,
            PRIMARY KEY (StockID, Month)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "green_energy_targets": """
        CREATE TABLE IF NOT EXISTS green_energy_targets (
            Year          INT          NOT NULL,
            Metric        VARCHAR(48)   NOT NULL,
            MetricLabel   VARCHAR(120),
            TargetValue   DECIMAL(14,2),
            ActualValue   DECIMAL(14,2),
            Unit          VARCHAR(24),
            Note          VARCHAR(255),
            SourceURL     VARCHAR(255),
            RetrievedDate DATE,
            PRIMARY KEY (Year, Metric)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
}


def ensure_tables(conn) -> None:
    """Create every table that does not exist yet."""
    with conn.cursor() as cursor:
        for _name, ddl in DDL.items():
            cursor.execute(ddl)
    conn.commit()
