FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN uv pip install --system --no-cache -r requirements.txt -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
