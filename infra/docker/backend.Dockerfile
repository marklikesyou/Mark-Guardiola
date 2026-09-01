FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --extra ml --extra sources --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev --extra ml --extra sources

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS runtime
ENV PATH=/app/backend/.venv/bin:$PATH PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/markguardiola-matplotlib SOCCERDATA_DIR=/app/data/raw/.soccerdata
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && apt-get clean
RUN groupadd --system mark && useradd --system --gid mark --home-dir /app mark
COPY --from=builder --chown=mark:mark /app/backend /app/backend
RUN mkdir -p /app/data /app/artifacts && chown -R mark:mark /app/data /app/artifacts
USER mark
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "markguardiola.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
