# Build from the repo root:  docker build -f services/web/Dockerfile -t athena-web .
FROM python:3.11-slim
WORKDIR /app

COPY services/web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/web/ .

ENV PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
