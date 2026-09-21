FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        libreoffice-writer \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles \
    && addgroup --system django \
    && adduser --system --ingroup django django \
    && chown -R django:django /app /tmp

USER django

EXPOSE 8000

CMD ["gunicorn", "dekstra.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
