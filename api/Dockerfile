FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY greenchainapi /app/greenchainapi

ENV PYTHONUNBUFFERED=1

EXPOSE 8888

CMD ["python", "-m", "uvicorn", "greenchainapi.main:app", "--host", "0.0.0.0", "--port", "8888"]
