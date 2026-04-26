# Stage 1: Build frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Stage 2: Build backend + serve frontend static files
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Copy frontend static build output
COPY --from=frontend-builder /frontend/out ./static

RUN mkdir -p /app/data/workspace /app/data/knowledge_base /app/data/sessions /app/data/skills

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
