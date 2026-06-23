FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlalchemy alembic pydantic pydantic-settings numpy scipy httpx aiosqlite python-dateutil

COPY app/ ./app/
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
