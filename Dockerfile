FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/alexfu/mcp-ynab
LABEL org.opencontainers.image.description="FastMCP server for the YNAB API"
LABEL org.opencontainers.image.licenses=MIT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --no-install-project

COPY main.py ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["python", "main.py"]
