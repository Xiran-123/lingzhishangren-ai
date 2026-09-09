FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn

COPY . .

RUN mkdir -p /app/data

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--worker-class", "gthread", "--threads", "8", "--worker-connections", "1000", "--timeout", "180", "--keep-alive", "5", "--no-sendfile", "app:app"]
