# Build from the repo root:  docker build -f services/monitor/Dockerfile -t athena-monitor .
FROM python:3.11-slim
WORKDIR /app

COPY services/monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/monitor/ .
COPY ml/drift.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
