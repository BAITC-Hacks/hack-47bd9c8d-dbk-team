FROM python:3.12-slim

# fonts-dejavu-core — TTF с кириллицей для экспорта summary в PDF:
# встроенные шрифты reportlab её не содержат.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY chunked_transcribe.py merge_transcript.py summarize_transcript.py export_pdf.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

VOLUME ["/data", "/artifacts"]

ENTRYPOINT ["./entrypoint.sh"]
