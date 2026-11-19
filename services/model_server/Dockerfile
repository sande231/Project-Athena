# Build from the repo root:  docker build -f services/model_server/Dockerfile -t athena-model-server .
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY services/model_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/model_server/ .
COPY ml/features.py .
ENV PYTHONUNBUFFERED=1 PORT=8001
EXPOSE 8001
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8001", "app:app"]
