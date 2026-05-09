# Base image with Python 3.12 + Playwright + Chromium pre-installed.
FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cache and output dirs (mounted to a Railway volume in production for
# persistence — auth_state.json + history must survive redeploys).
RUN mkdir -p /app/cache /app/output /app/logs

ENV PYTHONUNBUFFERED=1
ENV UPUP_AUTH_STATE=/app/cache/auth_state.json
ENV CACHE_DB_PATH=/app/cache/keywords.sqlite

CMD ["python", "-m", "tools.run_daily_all"]
