FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /srv/tripmate

# Non-root user with a home directory: uv keeps its tool cache there.
RUN useradd --create-home --uid 10001 tripmate

COPY requirements.txt .
# uv provides `uvx`, used to launch the AviationStack MCP server.
RUN pip install -r requirements.txt uv

COPY app ./app

USER tripmate
ENV PATH="/home/tripmate/.local/bin:${PATH}"

# Install the AviationStack MCP server at build time so the first request
# after a deploy does not have to download it (uvx reuses installed tools).
# It requires Python 3.13+, which uv downloads into its own environment.
RUN uv tool install aviationstack-mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"

# Render injects $PORT; proxy headers are trusted because Render terminates TLS.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
