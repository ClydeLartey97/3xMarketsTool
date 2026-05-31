FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY alembic.ini alembic.ini
COPY backend backend

EXPOSE 8000

CMD ["sh", "-c", "alembic -c /app/alembic.ini upgrade head && cd /app/backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
