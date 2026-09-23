FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY merge_transcript.py summarize_transcript.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

VOLUME ["/data", "/artifacts"]

ENTRYPOINT ["./entrypoint.sh"]
