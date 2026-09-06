"""
MySQL connection helper.

Uses pymysql + DictCursor, with a retry loop because the MySQL container may
still be initialising when an Airflow task first fires; without the retry the
task would fail immediately on "can't connect to database".
"""
import time
import pymysql
from loguru import logger

from ..config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE


def get_connection(retries: int = 10, delay_seconds: float = 3.0):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
            if attempt > 1:
                logger.info(f"MySQL connected (attempt {attempt})")
            return conn
        except Exception as e:  # noqa: BLE001 - want to retry on any connect error
            last_err = e
            logger.warning(
                f"MySQL connect failed (attempt {attempt}/{retries}): {e}; "
                f"retrying in {delay_seconds}s..."
            )
            time.sleep(delay_seconds)
    raise RuntimeError(f"Could not connect to MySQL after {retries} attempts: {last_err}")
