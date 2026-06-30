FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY *.py ./
COPY *.json.example ./
COPY templates/ templates/
COPY static/ static/

EXPOSE 5100

CMD ["gunicorn", "--bind", "0.0.0.0:5100", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "--timeout", "130", "wsgi:app"]
