# Backend: FastAPI + Playwright + MongoDB driver
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/pw-browsers

WORKDIR /app

# System deps for Playwright Chromium (font / X11 / NSS / ALSA / GTK libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates curl \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libgtk-3-0 libxshmfence1 libx11-xcb1 \
    fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt
# Playwright is excluded from requirements.txt to keep Emergent native deploy
# building cleanly. We install it explicitly here so Railway gets browser
# scraping (Vonovia) support.
RUN pip install playwright==1.49.0

# Playwright Chromium (browser binary)
RUN python -m playwright install --with-deps chromium

# App code
COPY . .

# Railway/Render inject $PORT; fall back to 8001 locally
ENV PORT=8001
EXPOSE 8001

# Production server
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
