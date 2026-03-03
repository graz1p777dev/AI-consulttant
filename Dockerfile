FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN python -m venv "$VIRTUAL_ENV" && \
    . "$VIRTUAL_ENV/bin/activate" && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    mkdir -p /app/data && \
    chown -R app:app /app

USER app

CMD ["python", "main.py"]
