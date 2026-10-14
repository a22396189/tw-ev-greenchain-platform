"""
Daily data-refresh DAG for the TW EV & Green-Energy supply-chain platform.

The crawler runs as a PythonOperator that imports and calls the `greenchain`
package directly, rather than a DockerOperator that would need the Docker socket
mounted into the Airflow container. Same "scheduled + containerised" pipeline,
without the docker-in-docker layer that tends to be fragile on Windows Docker
Desktop.

The `greenchain` package is mounted into this container at
/opt/airflow/dags/greenchain (see docker-compose.yml), so the import below
resolves.
"""
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "green-energy-data",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


def _run_task(task_name: str):
    # import lazily so the DAG file still parses before the package is installed
    from greenchain.main import run_task
    run_task(task_name)


with DAG(
    dag_id="greenchain_data_pipeline",
    description="Daily refresh: price / institutional flows / margins / revenue for the EV & green-energy basket",
    # A tz-aware start_date makes Airflow evaluate the cron in Taiwan time. The container's
    # TZ env var does NOT affect scheduling: without this, "0 21 * * 1-5" is read as
    # 21:00 UTC, i.e. 05:00 the next morning in Taipei.
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Taipei"),
    schedule="0 21 * * 1-5",  # weekdays 21:00 Asia/Taipei (after the TWSE close + T86 publication)
    catchup=False,
    max_active_runs=1,
    tags=["green-energy", "ev", "market-data"],
    default_args=default_args,
) as dag:

    task_stock_price = PythonOperator(
        task_id="update_stock_price",
        python_callable=_run_task,
        op_args=["stock_price"],
    )

    task_institutional_investor = PythonOperator(
        task_id="update_institutional_investor",
        python_callable=_run_task,
        op_args=["institutional_investor"],
    )

    task_quarterly_margins = PythonOperator(
        task_id="update_quarterly_margins",
        python_callable=_run_task,
        op_args=["quarterly_margins"],
    )

    task_monthly_revenue = PythonOperator(
        task_id="update_monthly_revenue",
        python_callable=_run_task,
        op_args=["monthly_revenue"],
    )

    # independent tasks (each writes a different table) - run in parallel
    [task_stock_price, task_institutional_investor, task_quarterly_margins, task_monthly_revenue]
