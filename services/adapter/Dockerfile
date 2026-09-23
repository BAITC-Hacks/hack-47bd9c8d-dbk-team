FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir kafka-python-ng minio
COPY adapter.py .
CMD ["python3", "-u", "adapter.py"]
