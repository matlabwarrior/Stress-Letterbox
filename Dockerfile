# ============================================================
# Workplace Stress Letterbox — Server Dockerfile
# ============================================================
# Build:   docker build -t stress-letterbox .
# Run:     docker run -d \
#            --name stress-letterbox \
#            -p 5000:5000 \
#            -v /opt/letterbox-data:/app/server/data \
#            -v /opt/letterbox-config/config.yaml:/app/config.yaml:ro \
#            stress-letterbox
# ============================================================

FROM python:3.12-slim

# Security: don't run as root
RUN useradd --create-home --shell /bin/bash letterbox
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy application code
COPY server/ ./server/
COPY shared/ ./shared/
# config.yaml is mounted as a volume at runtime — not baked into the image

# Create data directory with correct ownership
RUN mkdir -p server/data server/data/floorplans && \
    chown -R letterbox:letterbox /app

USER letterbox

EXPOSE 5000

# Healthcheck: verify the departments endpoint responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/departments')" || exit 1

# python server/app.py runs Flask's own dev server, which logs a warning
# against exactly this kind of use ("do not use in a production deployment").
# "server.app:create_app()" — the trailing () tells gunicorn to call it as
# a factory rather than treat it as an app instance.
# Single worker + multiple threads: the in-memory rate limiter (see
# server/extensions.py) only agrees with itself within one process — scale
# via --threads, not --workers, unless a shared backend (e.g. Redis) is
# also configured for it.
CMD ["gunicorn", "server.app:create_app()", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4"]
