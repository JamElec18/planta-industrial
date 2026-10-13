# Imagen con Python + Java (Spark corre sobre la JVM) + PySpark.
# Así no tienes que instalar Java ni Spark en tu Mac.
FROM python:3.12-slim

# ── PASO 1 · Java y utilidades que necesitan los scripts de Spark ────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless procps \
    && rm -rf /var/lib/apt/lists/*

# ── PASO 2 · Dependencias de Python ──────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── PASO 3 · Código ──────────────────────────────────────────────────────────
COPY . .

# ── PASO 4 · Por defecto: generar los datos y correr el ETL ──────────────────
CMD ["sh", "-c", "python generar_datos.py && python etl.py"]
