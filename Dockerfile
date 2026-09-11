FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY api ./api
COPY caching ./caching
COPY clarify ./clarify
COPY compression ./compression
COPY graph.py ./graph.py
COPY infra ./infra
COPY reporting ./reporting
COPY research_brief ./research_brief
COPY researcher ./researcher
COPY state ./state
COPY supervisor ./supervisor
COPY verification ./verification

RUN uv sync --frozen --no-dev --extra production

COPY config ./config

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
