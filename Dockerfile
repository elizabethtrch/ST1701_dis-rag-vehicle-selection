FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Código fuente
COPY src/ ./src/
COPY main.py .
COPY data/ ./data/

# Variables de entorno por defecto
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV LOG_LEVEL=INFO
ENV CHROMA_PATH=/app/data/chroma_db
ENV KNOWLEDGE_BASE_PATH=/app/data/knowledge_base

EXPOSE 8000

# Seed automático + arranque del servidor
CMD ["sh", "-c", "python -m src.adapters.input.cli.ingest_cli seed && python main.py"]
