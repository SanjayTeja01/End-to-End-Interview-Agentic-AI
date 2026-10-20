FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# libmagic for server-side MIME sniffing, ffmpeg for audio normalisation (STT)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-speech.txt ./
RUN pip install -r requirements.txt && pip install -r requirements-speech.txt

COPY . .

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

# Bake the local embedding model (all-MiniLM-L6-v2, ~80 MB) into the image so first use is instant.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as F; F()(['warm up'])" \
    || echo "embedding model will be downloaded on first use"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
