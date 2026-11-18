FROM python:3.11-slim as base

# Evita criação de arquivos .pyc e força flush imediato nos logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala dependências de compilação essenciais e certificados SSL CA
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Estrutura o pacote backend.app para compatibilidade absoluta com os imports
RUN mkdir -p /app/backend
COPY app ./backend/app
RUN touch /app/backend/__init__.py
RUN ln -s /app/backend/app /app/app

# Adiciona /app ao PYTHONPATH
ENV PYTHONPATH=/app

# Usuário não-root para segurança
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Execução do Uvicorn apontando para backend.app.main:app
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
