# Build from the repo root:  docker build -f services/api/Dockerfile -t athena-api .
FROM python:3.11-slim
WORKDIR /app

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/ .

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
