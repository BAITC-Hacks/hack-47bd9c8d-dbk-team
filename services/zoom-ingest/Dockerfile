FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY zoom_ingest ./zoom_ingest

# Режим по умолчанию — поллер облачных записей (бесконечный цикл).
CMD ["python", "-m", "zoom_ingest", "poll"]
