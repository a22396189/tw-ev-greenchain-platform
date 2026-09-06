# The build context is the project root (see docker-compose.yml build.context),
# so the image can pick up both crawler/ code and the root-level data_seed/ CSVs.
FROM python:3.12-slim

WORKDIR /app

COPY crawler/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY crawler/greenchain /app/greenchain
COPY data_seed /app/data_seed

ENV SEED_DIR=/app/data_seed
ENV PYTHONUNBUFFERED=1

# This container is not a long-running service; it is invoked briefly by Airflow
# or by `docker compose run`. The default command just prints usage so an
# accidental `docker compose up` does not spin-restart forever.
CMD ["python", "-c", "print('usage: docker compose run --rm crawler python -m greenchain.seed  |  python -m greenchain.main <task>')"]
