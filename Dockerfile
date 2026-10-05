# Una sola imagen para simulador y collector; docker-compose decide qué comando corre cada uno.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY simulator ./simulator
COPY collector ./collector
