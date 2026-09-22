FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv build --wheel && uv export --frozen --no-dev --no-emit-project --no-hashes -o requirements.txt
RUN uv venv /opt/venv && uv pip install --python /opt/venv/bin/python -r requirements.txt dist/*.whl

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser
COPY --from=builder /opt/venv /opt/venv
COPY scripts/smoke.py /opt/pcvmf-smoke.py
USER appuser
WORKDIR /home/appuser
CMD ["pcvmf", "run"]
