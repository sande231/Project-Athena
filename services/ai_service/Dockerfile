# Build from the repo root:  docker build -f services/ai_service/Dockerfile -t athena-ai-service .
FROM python:3.11-slim
WORKDIR /app

COPY services/ai_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/ai_service/ .

ENV PYTHONUNBUFFERED=1 PORT=8002
EXPOSE 8002
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8002", "app:app"]
