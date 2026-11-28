FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv==0.5.11
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN uv pip install --system --no-cache -r requirements.txt -r requirements-dev.txt
COPY . .
# Sha curto do commit publicado (ci.yml passa --build-arg GIT_SHA=${GITHUB_SHA::7}); "dev" num build
# local. /health expõe isso para o smoke test confirmar qual commit está no ar (a tag :latest é mutável).
ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
