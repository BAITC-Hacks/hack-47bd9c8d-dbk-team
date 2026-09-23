# Диаризация (кто когда говорил) и опознание говорящего по образцу голоса.
#
# Две модели NeMo резидентно: Sortformer ~25 с на загрузку, TitaNet ~10 с,
# вместе ~0.7 ГБ VRAM. Держатся в памяти, поэтому запрос не платит за загрузку,
# а `/health` до готовности честно отвечает "loading" — на это и надо ждать
# при старте, а не на появление процесса.
FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-dev python3-venv python3-pip \
        curl ca-certificates ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY *.py /app/

# Веса NeMo тянутся с хаба при ПЕРВОМ старте в этот кэш. Он вынесен томом:
# иначе каждый `docker rm` стоил бы повторной загрузки, а на плохом канале
# это минуты перед каждым запуском.
ENV HF_HOME=/cache/hf
ENV NEMO_CACHE_DIR=/cache/nemo
ENV DIAR_DATA_DIR=/data

# Карта общая с распознаванием — фрагментация аллокатора здесь дороже, чем
# сами 0.7 ГБ.
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
ENV DIAR_PORT=8000
ENV DIAR_DEVICE=cuda:0

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s \
    CMD curl -fsS http://localhost:8000/health | grep -q '"status":"healthy"' || exit 1
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
