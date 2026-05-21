FROM python:3.11-slim

WORKDIR /app

# gcc necesario para compilar asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Producción: sin --reload, workers = 2 (Railway tiene 2 vCPU en free tier)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
