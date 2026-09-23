# Распознавание речи: faster-whisper на CTranslate2.
#
# База с CUDA 13, а CTranslate2 собран под CUDA 12 — поэтому рантайм CUDA 12
# приезжает колёсами pip, и config.py подгружает его по абсолютному пути ДО
# того, как faster-whisper попросит библиотеки у линковщика. Без этого
# контейнер стартует и падает на первой же расшифровке.
FROM nvidia/cuda:13.1.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-dev python3-venv python3-pip \
        curl ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH

RUN pip install --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cu130
RUN pip install --no-cache-dir \
        faster-whisper ctranslate2 transformers huggingface_hub \
        fastapi uvicorn python-multipart pydantic librosa soundfile numpy

WORKDIR /app

# Веса кладутся в СЛОЙ ОБРАЗА, а не в том. Причина практическая: том пережил бы
# `docker rm`, но при этом молча разъехался бы с кодом, который его читает.
# Нужен внешний каталог с моделями — примонтируйте его и переопределите
# WHISPER_*_CT2_PATH; см. README.
ARG STT_MODELS=large-v3,large-v3-turbo
ENV STT_MODELS=${STT_MODELS}
COPY download_models.py /tmp/download_models.py
RUN python3 /tmp/download_models.py && rm /tmp/download_models.py

COPY *.py /app/

ENV PORT=8000
ENV DEVICE=cuda:0
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
